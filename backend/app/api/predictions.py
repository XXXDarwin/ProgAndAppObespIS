from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AnyAuthenticatedUser, CurrentUser, ManagerOrAbove
from app.db.database import get_db
from app.schemas.ml import (
    DemandHistoryImport,
    DemandHistoryImportResult,
    ForecastMethodInfo,
    ForecastOverview,
    ForecastResponse,
    ModelInfo,
    TrainRequest,
    TrainStatus,
    ValidateCompareRequest,
    ValidateCompareResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.services.history_import_service import import_demand_history
from app.services.ml_forecast_methods import list_forecast_methods, normalize_forecast_method
from app.services.ml_service import (
    generate_forecast,
    get_forecast_overview,
    get_models_info,
    get_train_status,
    run_all_methods_validation,
    run_model_validation,
    run_training_task,
)

router = APIRouter()


# ─── Training ─────────────────────────────────────────────────────────────────

@router.post(
    "/train",
    response_model=TrainStatus,
    summary="Запустить обучение моделей",
    dependencies=[ManagerOrAbove],
)
async def start_training(
    data: TrainRequest,
    background_tasks: BackgroundTasks,
):
    """
    Запускает обучение XGBoost в фоне (BackgroundTasks).
    Не блокирует запрос — статус можно проверить через GET /train/status.
    product_ids = null → обучить все активные товары.
    force = true → переобучить даже актуальные модели.
    """
    status = get_train_status()
    if status.status == "running":
        return status   # уже идёт, не запускаем второй раз

    background_tasks.add_task(
        run_training_task,
        data.product_ids,
        data.force,
        data.category_id,
    )
    return TrainStatus(status="running")


@router.get(
    "/train/status",
    response_model=TrainStatus,
    summary="Статус обучения",
)
async def training_status(_: Annotated[None, AnyAuthenticatedUser]):
    """Возвращает текущий статус фонового обучения."""
    return get_train_status()


# ─── Forecast methods ───────────────────────────────────────────────────────────

@router.get(
    "/methods",
    response_model=List[ForecastMethodInfo],
    summary="Доступные методы прогнозирования",
)
async def forecast_methods(_: Annotated[None, AnyAuthenticatedUser]):
    """Список ML и статистических методов для прогноза и валидации."""
    return list_forecast_methods()


# ─── Forecast ─────────────────────────────────────────────────────────────────

@router.get(
    "/forecast/{product_id}",
    response_model=ForecastResponse,
    summary="Прогноз спроса по товару",
)
async def get_forecast(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
    days: int = Query(14, ge=7, le=30, description="Горизонт прогноза в днях"),
    method: str = Query(
        "xgboost",
        description="Метод: xgboost, moving_average, exponential_smoothing, holt, arima",
    ),
):
    """
    Прогноз на N дней вперёд + история за 60 дней.
    XGBoost требует POST /train; статистические методы работают по истории расхода.
    """
    try:
        normalize_forecast_method(method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await generate_forecast(product_id, days, db, forecast_method=method)


# ─── Models info ──────────────────────────────────────────────────────────────

@router.get(
    "/overview",
    response_model=ForecastOverview,
    summary="Сводка по прогнозированию",
    dependencies=[ManagerOrAbove],
)
async def forecast_overview(db: Annotated[AsyncSession, Depends(get_db)]):
    """Агрегированная статистика: модели, история спроса, разбивка по категориям."""
    return await get_forecast_overview(db)


@router.get(
    "/models",
    response_model=List[ModelInfo],
    summary="Статус моделей по товарам",
    dependencies=[ManagerOrAbove],
)
async def list_models(
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: Optional[int] = Query(None, description="Фильтр по категории"),
):
    return await get_models_info(db, category_id=category_id)


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Holdout-валидация моделей (MAE, RMSE, MAPE, R²)",
    dependencies=[ManagerOrAbove],
)
async def validate_models(
    data: ValidateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Хронологическое разделение ряда спроса (CONSUMPTION), обучение XGBoost на train,
    walk-forward прогноз на test, расчёт метрик качества по SKU.
    """
    return await run_model_validation(
        db, data.product_id, data.test_size, data.forecast_method
    )


@router.post(
    "/validate/compare",
    response_model=ValidateCompareResponse,
    summary="Сравнение holdout-метрик по всем методам прогноза",
    dependencies=[ManagerOrAbove],
)
async def validate_models_compare(
    data: ValidateCompareRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Одна загрузка истории спроса, затем holdout-валидация для каждого доступного метода.
    Сводка отсортирована по среднему MAE (лучшие выше).
    """
    return await run_all_methods_validation(db, data.product_id, data.test_size)


@router.post(
    "/history/import",
    response_model=DemandHistoryImportResult,
    summary="Импорт синтетической истории спроса",
    dependencies=[ManagerOrAbove],
)
async def import_history(
    payload: DemandHistoryImport,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Загружает дневной спрос (sku, date, quantity) как завершённые заказы расхода.
    Используется для обучения прогноза после генерации в data-generator.
    """
    return await import_demand_history(payload, db, actor=current_user)

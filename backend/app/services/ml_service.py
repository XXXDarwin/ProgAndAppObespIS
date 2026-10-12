"""
ML Service: обучение XGBoost и генерация прогнозов спроса.

Модели сохраняются в /app/ml_models/{product_id}.json
Статус обучения хранится в памяти (достаточно для одного процесса).
"""

import asyncio
import json
import logging
import os
import pickle
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import partial
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.models import (
    Order, OrderItem, OrderStatus, OrderType, Product, Prediction, Stock,
)
from app.schemas.ml import (
    CategoryBrief,
    CategoryModelSummary,
    CategoryValidationSummary,
    ForecastInsight,
    ForecastOverview,
    ForecastPoint,
    ForecastResponse,
    ModelInfo,
    TrainStatus,
    MethodValidationRun,
    ValidateCompareResponse,
    ValidateResponse,
    ValidationMetrics,
)
from app.services.ml_features import (
    inverse_transform_target,
    prepare_forecast_data,
    prepare_train_data,
    transform_target,
)
from app.services.ml_forecast_methods import (
    DEFAULT_METHOD,
    forecast_statistical,
    list_forecast_methods,
    min_days_for_method,
    normalize_forecast_method,
    validate_holdout_statistical,
)

logger = logging.getLogger(__name__)

# ─── Пути ─────────────────────────────────────────────────────────────────────

MODELS_DIR = Path("/app/ml_models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MIN_DATA_POINTS = 14          # минимум дней в ряду для участия в глобальном обучении
CONFIDENCE_ALPHA = 1.28       # ~80% доверительный интервал (1.28 σ)

XGB_PARAMS = {
    "n_estimators": 400,
    "max_depth": 3,
    "learning_rate": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "reg_alpha": 0.5,
    "random_state": 42,
    "n_jobs": -1,
    "verbosity": 0,
}

# ─── Глобальный статус обучения ───────────────────────────────────────────────

_train_status = TrainStatus(status="idle")


def get_train_status() -> TrainStatus:
    return _train_status


def _model_path(product_id: int) -> Path:
    return MODELS_DIR / f"product_{product_id}.pkl"


def _meta_path(product_id: int) -> Path:
    return MODELS_DIR / f"product_{product_id}_meta.json"


def _global_model_path() -> Path:
    return MODELS_DIR / "global_xgb.pkl"


def _global_meta_path() -> Path:
    return MODELS_DIR / "global_xgb_meta.json"


# ─── Data loading ─────────────────────────────────────────────────────────────

def _rows_to_demand_series(rows: list[tuple]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    data: dict[str, float] = {}
    for closed_at, qty in rows:
        day = closed_at.date() if hasattr(closed_at, "date") else closed_at
        key = str(day)
        data[key] = data.get(key, 0) + float(qty)
    series = pd.Series(data)
    series.index = pd.to_datetime(series.index)
    return series.sort_index().astype(float)


async def _load_demand_rows(
    db: AsyncSession,
    product_ids: Optional[list[int]] = None,
) -> list[tuple[int, datetime, int]]:
    """Строки (product_id, closed_at, quantity) по завершённым расходам."""
    q = (
        select(OrderItem.product_id, Order.closed_at, OrderItem.quantity)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.type == OrderType.CONSUMPTION,
            Order.status == OrderStatus.COMPLETED,
            Order.closed_at.isnot(None),
        )
    )
    if product_ids:
        q = q.where(OrderItem.product_id.in_(product_ids))
    result = await db.execute(q.order_by(Order.closed_at))
    return result.all()


async def _load_demand_series(product_id: int, db: AsyncSession) -> pd.Series:
    """
    Дневной спрос: только завершённые заказы расхода (включая импорт истории).
    """
    rows = await _load_demand_rows(db, [product_id])
    return _rows_to_demand_series([(r[1], r[2]) for r in rows])


async def _load_demand_series_bulk(
    db: AsyncSession,
    product_ids: list[int],
) -> dict[int, pd.Series]:
    if not product_ids:
        return {}
    rows = await _load_demand_rows(db, product_ids)
    by_product: dict[int, list[tuple]] = {pid: [] for pid in product_ids}
    for pid, closed_at, qty in rows:
        by_product.setdefault(pid, []).append((closed_at, qty))
    return {pid: _rows_to_demand_series(items) for pid, items in by_product.items()}


async def _get_stock_totals(db: AsyncSession, product_ids: list[int]) -> dict[int, int]:
    if not product_ids:
        return {}
    result = await db.execute(
        select(Stock.product_id, func.coalesce(func.sum(Stock.quantity), 0))
        .where(Stock.product_id.in_(product_ids), Stock.quantity > 0)
        .group_by(Stock.product_id)
    )
    return {int(pid): int(total) for pid, total in result.all()}


def _build_insights(
    series: pd.Series,
    forecast_points: list[ForecastPoint],
    total_stock: int,
    horizon_days: int,
) -> ForecastInsight:
    last_14 = series.tail(14) if len(series) else pd.Series(dtype=float)
    avg_14 = float(last_14.mean()) if len(last_14) else 0.0
    forecast_total = sum(p.predicted for p in forecast_points)
    forecast_avg = forecast_total / horizon_days if horizon_days else 0.0
    daily_need = forecast_avg if forecast_avg > 0 else avg_14

    days_until: Optional[float] = None
    recommendation = "Достаточно данных для планирования закупки."
    if total_stock <= 0 and daily_need > 0:
        days_until = 0.0
        recommendation = "Остаток нулевой — требуется закупка."
    elif daily_need > 0:
        days_until = round(total_stock / daily_need, 1)
        if days_until < 7:
            recommendation = f"Критично: запаса хватит ~{days_until} дн. — планируйте закупку."
        elif days_until < horizon_days:
            recommendation = f"Запаса хватит ~{days_until} дн. — закупка до конца горизонта ({horizon_days} дн.)."
        else:
            recommendation = f"Запаса хватит более {horizon_days} дн. при текущем прогнозе."

    return ForecastInsight(
        total_stock=total_stock,
        avg_daily_demand_14d=round(avg_14, 2),
        forecast_total=round(forecast_total, 2),
        forecast_avg_daily=round(forecast_avg, 2),
        days_until_stockout=days_until,
        recommendation=recommendation,
    )


# ─── Training ─────────────────────────────────────────────────────────────────

def _make_xgb_regressor():
    import xgboost as xgb
    return xgb.XGBRegressor(**XGB_PARAMS)


def _fit_xgb(model, X: pd.DataFrame, y: pd.Series) -> float:
    """Обучение на log(1+y), residual_std в исходной шкале."""
    y_log = transform_target(y)
    model.fit(X, y_log)
    preds = inverse_transform_target(model.predict(X))
    residual_std = float(np.std(y.values - preds))
    return residual_std


def _train_model(
    series: pd.Series,
    product_id: int | None = None,
    category_id: int | None = None,
) -> tuple:
    """Обучает XGBoost на одном ряду (fallback без глобальной модели)."""
    X, y = prepare_train_data(series, product_id=product_id, category_id=category_id)
    if len(X) < MIN_DATA_POINTS:
        raise ValueError(f"Недостаточно данных: {len(X)} дней (нужно ≥ {MIN_DATA_POINTS})")

    model = _make_xgb_regressor()
    residual_std = _fit_xgb(model, X, y)
    return model, residual_std


def _train_global_model(
    entries: list[tuple[pd.Series, int, int | None]],
) -> tuple:
    """
    Одна модель на весь каталог: entries = [(series, product_id, category_id), ...].
    """
    if not entries:
        raise ValueError("Нет товаров для глобального обучения")

    frames_x: list[pd.DataFrame] = []
    frames_y: list[pd.Series] = []
    for series, pid, cid in entries:
        X, y = prepare_train_data(series, product_id=pid, category_id=cid or 0)
        if len(X) < 1:
            continue
        frames_x.append(X)
        frames_y.append(y)

    if not frames_x:
        raise ValueError("Недостаточно строк для глобального обучения")

    X_all = pd.concat(frames_x, ignore_index=True)
    y_all = pd.concat(frames_y, ignore_index=True)
    if len(X_all) < MIN_DATA_POINTS:
        raise ValueError(f"Недостаточно данных: {len(X_all)} строк")

    model = _make_xgb_regressor()
    residual_std = _fit_xgb(model, X_all, y_all)
    return model, residual_std, len(entries)


def _save_global_model(model, residual_std: float, products_in_model: int) -> dict:
    with open(_global_model_path(), "wb") as f:
        pickle.dump(model, f)
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "model_version": f"xgb-global-v2-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "products_in_model": products_in_model,
        "residual_std": residual_std,
        "log_target": True,
    }
    with open(_global_meta_path(), "w") as f:
        json.dump(meta, f)
    return meta


def _load_global_model() -> tuple:
    path = _global_model_path()
    meta_path = _global_meta_path()
    if not path.exists():
        raise FileNotFoundError("Глобальная модель не найдена. Запустите обучение.")
    with open(path, "rb") as f:
        model = pickle.load(f)
    with open(meta_path) as f:
        meta = json.load(f)
    return model, meta


async def _collect_training_entries(
    db: AsyncSession,
    product_ids: list[int],
) -> list[tuple[pd.Series, int, int | None]]:
    if not product_ids:
        return []
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.id.in_(product_ids), Product.is_active.is_(True))
    )
    products = {p.id: p for p in result.scalars().all()}
    demand_map = await _load_demand_series_bulk(db, product_ids)
    entries: list[tuple[pd.Series, int, int | None]] = []
    for pid in product_ids:
        series = demand_map.get(pid, pd.Series(dtype=float))
        if len(series) < MIN_DATA_POINTS:
            continue
        p = products.get(pid)
        cid = p.category_id if p and p.category_id else 0
        entries.append((series, pid, cid))
    return entries


async def train_global_catalog(db: AsyncSession, product_ids: list[int]) -> dict:
    """Обучает единую XGBoost-модель по всем переданным SKU."""
    entries = await _collect_training_entries(db, product_ids)
    if not entries:
        return {"status": "skipped", "reason": "not_enough_data", "products_in_model": 0}

    loop = asyncio.get_event_loop()
    model, residual_std, n_products = await loop.run_in_executor(
        None, lambda: _train_global_model(entries)
    )
    meta = _save_global_model(model, residual_std, n_products)
    return {"status": "trained", **meta}


async def train_product(product_id: int, db: AsyncSession) -> dict:
    """Переобучает глобальную модель по всему активному каталогу (товар включается в пул)."""
    result = await db.execute(
        select(Product.id).where(Product.is_active.is_(True))
    )
    ids = [row[0] for row in result.all()]
    if product_id not in ids:
        ids.append(product_id)

    out = await train_global_catalog(db, ids)
    if out.get("status") != "trained":
        series = await _load_demand_series(product_id, db)
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": out.get("reason", "not_enough_data"),
            "data_points": len(series),
        }

    series = await _load_demand_series(product_id, db)
    return {
        "product_id": product_id,
        "status": "trained",
        "model_scope": "global",
        "data_points": len(series),
        **{k: v for k, v in out.items() if k != "status"},
    }


# ─── Background training task ─────────────────────────────────────────────────

async def run_training_task(
    product_ids: Optional[list[int]] = None,
    force: bool = False,
    category_id: Optional[int] = None,
):
    """
    Фоновая задача обучения (запускается через BackgroundTasks).
    Использует отдельную сессию БД.
    """
    global _train_status

    _train_status = TrainStatus(status="running", started_at=datetime.now(timezone.utc))

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    trained = 0
    error_msg = None

    try:
        async with SessionLocal() as db:
            # Определяем список товаров для обучения
            if product_ids:
                ids = product_ids
            else:
                q = select(Product.id).where(Product.is_active.is_(True))
                if category_id is not None:
                    q = q.where(Product.category_id == category_id)
                result = await db.execute(q)
                ids = [row[0] for row in result.all()]

            if not force and _global_meta_path().exists():
                with open(_global_meta_path()) as f:
                    gmeta = json.load(f)
                trained_at = datetime.fromisoformat(gmeta["trained_at"])
                if (datetime.now(timezone.utc) - trained_at).days < 1:
                    ids = []

            if ids:
                try:
                    result = await train_global_catalog(db, ids)
                    if result.get("status") == "trained":
                        trained = result.get("products_in_model", 0)
                        logger.info(
                            f"Глобальная XGBoost: {trained} SKU, version={result.get('model_version')}"
                        )
                except Exception as e:
                    logger.warning(f"Ошибка глобального обучения: {e}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка задачи обучения: {e}")
    finally:
        await engine.dispose()

    _train_status = TrainStatus(
        status="error" if error_msg else "done",
        started_at=_train_status.started_at,
        finished_at=datetime.now(timezone.utc),
        products_trained=trained,
        error=error_msg,
    )


# ─── Forecasting ──────────────────────────────────────────────────────────────

def _load_model(product_id: int) -> tuple:
    """Загружает per-SKU модель (legacy fallback)."""
    model_path = _model_path(product_id)
    meta_path = _meta_path(product_id)

    if not model_path.exists():
        raise FileNotFoundError(f"Модель для product_id={product_id} не найдена. Запустите обучение.")

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    with open(meta_path) as f:
        meta = json.load(f)

    return model, meta


def _prediction_from_raw(raw: float, use_log_target: bool) -> float:
    if use_log_target:
        return float(inverse_transform_target([raw])[0])
    return max(0.0, float(raw))


def _make_forecast(
    model,
    series: pd.Series,
    residual_std: float,
    horizon: int,
    product_id: int | None = None,
    category_id: int | None = None,
    use_log_target: bool = True,
) -> list[ForecastPoint]:
    """Итеративный прогноз с признаками SKU/категории для глобальной модели."""
    extended = series.copy().astype(float)
    points = []

    for _ in range(horizon):
        forecast_df = prepare_forecast_data(
            extended, horizon=1, product_id=product_id, category_id=category_id
        )
        if forecast_df.empty:
            break

        raw = float(model.predict(forecast_df)[0])
        pred = _prediction_from_raw(raw, use_log_target)

        target_date = extended.index.max() + timedelta(days=1)
        extended.loc[target_date] = pred

        margin = CONFIDENCE_ALPHA * residual_std
        points.append(ForecastPoint(
            date=str(target_date.date()),
            predicted=round(pred, 2),
            lower=round(max(0.0, pred - margin), 2),
            upper=round(pred + margin, 2),
        ))

    return points


def _method_label(method: str) -> str:
    for m in list_forecast_methods():
        if m.id == method:
            return m.label
    return method


async def generate_forecast(
    product_id: int,
    days: int,
    db: AsyncSession,
    forecast_method: str = DEFAULT_METHOD,
) -> ForecastResponse:
    """Генерирует прогноз спроса на `days` дней вперёд."""
    from fastapi import HTTPException

    try:
        method = normalize_forecast_method(forecast_method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if not product.is_active:
        raise HTTPException(status_code=400, detail="Товар деактивирован")

    series = await _load_demand_series(product_id, db)
    if series.empty:
        raise HTTPException(status_code=400, detail="Нет исторических данных для прогноза")

    loop = asyncio.get_event_loop()
    model_version: Optional[str] = None

    if method == "xgboost":
        category_id = product.category_id if product.category_id else 0
        try:
            model, meta = _load_global_model()
            model_version = meta.get("model_version")
            residual_std = meta.get("residual_std", 1.0)
            use_log = meta.get("log_target", True)
            forecast_points = await loop.run_in_executor(
                None,
                partial(
                    _make_forecast,
                    model,
                    series,
                    residual_std,
                    days,
                    product_id,
                    category_id,
                    use_log,
                ),
            )
        except FileNotFoundError:
            try:
                model, meta = _load_model(product_id)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            residual_std = meta.get("residual_std", 1.0)
            use_log = meta.get("log_target", False)
            forecast_points = await loop.run_in_executor(
                None,
                partial(
                    _make_forecast,
                    model,
                    series,
                    residual_std,
                    days,
                    None,
                    None,
                    use_log,
                ),
            )
            model_version = meta.get("model_version")
    else:
        try:
            forecast_points = await loop.run_in_executor(
                None, forecast_statistical, method, series, days
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        model_version = f"{method}-v1-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    history_series = series.tail(60)
    history = [
        ForecastPoint(
            date=str(d.date()),
            predicted=float(v),
            lower=float(v),
            upper=float(v),
        )
        for d, v in history_series.items()
    ]

    stocks = await _get_stock_totals(db, [product_id])
    total_stock = stocks.get(product_id, 0)
    insights = _build_insights(series, forecast_points, total_stock, days)

    await _save_predictions(product_id, forecast_points, model_version, db)

    category_out = None
    if product.category:
        category_out = CategoryBrief.model_validate(product.category)

    return ForecastResponse(
        product_id=product_id,
        product_sku=product.sku,
        product_name=product.name,
        category=category_out,
        horizon_days=days,
        forecast_method=method,
        forecast_method_label=_method_label(method),
        model_version=model_version,
        generated_at=datetime.now(timezone.utc),
        data_points_total=len(series),
        forecast=forecast_points,
        history=history,
        insights=insights,
    )


async def _save_predictions(
    product_id: int,
    points: list[ForecastPoint],
    model_version: Optional[str],
    db: AsyncSession,
) -> None:
    """Сохраняет прогноз в таблицу Prediction."""
    from sqlalchemy import delete
    from app.models.models import Prediction

    # Удаляем старые прогнозы для этого товара
    await db.execute(delete(Prediction).where(Prediction.product_id == product_id))

    for point in points:
        db.add(Prediction(
            product_id=product_id,
            target_date=datetime.fromisoformat(point.date),
            predicted_value=point.predicted,
            lower_bound=point.lower,
            upper_bound=point.upper,
            model_version=model_version,
        ))
    await db.commit()


# ─── Model info ───────────────────────────────────────────────────────────────

async def get_models_info(
    db: AsyncSession,
    category_id: Optional[int] = None,
) -> list[ModelInfo]:
    q = (
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.is_active.is_(True))
        .order_by(Product.sku)
    )
    if category_id is not None:
        q = q.where(Product.category_id == category_id)

    result = await db.execute(q)
    products = result.scalars().all()
    if not products:
        return []

    pids = [p.id for p in products]
    demand_map = await _load_demand_series_bulk(db, pids)
    stock_map = await _get_stock_totals(db, pids)

    global_meta: dict = {}
    global_ready = _global_meta_path().exists()
    if global_ready:
        with open(_global_meta_path()) as f:
            global_meta = json.load(f)

    infos: list[ModelInfo] = []
    for product in products:
        pid = product.id
        series = demand_map.get(pid, pd.Series(dtype=float))
        history_days = len(series)
        ready = global_ready or _model_path(pid).exists()
        meta: dict = global_meta if global_ready else {}
        if not global_ready and _meta_path(pid).exists():
            with open(_meta_path(pid)) as f:
                meta = json.load(f)

        category_out = (
            CategoryBrief.model_validate(product.category) if product.category else None
        )
        trained_at = meta.get("trained_at")
        infos.append(ModelInfo(
            product_id=pid,
            product_sku=product.sku,
            product_name=product.name,
            category=category_out,
            total_stock=stock_map.get(pid, 0),
            history_days=history_days,
            trained_at=datetime.fromisoformat(trained_at) if trained_at else None,
            model_version=meta.get("model_version"),
            data_points=meta.get("data_points", history_days),
            ready=ready,
            can_train=history_days >= MIN_DATA_POINTS,
        ))

    return infos


async def get_forecast_overview(db: AsyncSession) -> ForecastOverview:
    models = await get_models_info(db)
    ready = sum(1 for m in models if m.ready)
    history_ready = sum(1 for m in models if m.can_train)
    status = get_train_status()

    by_cat: dict[Optional[int], CategoryModelSummary] = {}
    for m in models:
        cid = m.category.id if m.category else None
        cname = m.category.name if m.category else "Без категории"
        if cid not in by_cat:
            by_cat[cid] = CategoryModelSummary(
                category_id=cid,
                category_name=cname,
                products_count=0,
                models_ready=0,
                history_ready=0,
            )
        row = by_cat[cid]
        row.products_count += 1
        if m.ready:
            row.models_ready += 1
        if m.can_train:
            row.history_ready += 1

    categories = sorted(by_cat.values(), key=lambda c: c.category_name)

    return ForecastOverview(
        total_products=len(models),
        models_ready=ready,
        models_pending=len(models) - ready,
        history_ready=history_ready,
        training_status=status.status,
        products_trained_last_run=status.products_trained,
        categories=categories,
    )


# ─── Holdout validation ───────────────────────────────────────────────────────

MIN_VALIDATION_DAYS = 42   # ~28 лагов + 14 дней обучения


def _normalize_daily_series(series: pd.Series) -> pd.Series:
    series = series.copy()
    series.index = pd.to_datetime(series.index)
    series = series.sort_index()
    if series.empty:
        return series
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq="D")
    return series.reindex(full_idx, fill_value=0).astype(float)


def _chronological_split(series: pd.Series, test_size: float) -> tuple[pd.Series, pd.Series]:
    """Разделение ряда без перемешивания: train | test."""
    series = _normalize_daily_series(series)
    n = len(series)
    test_count = max(1, int(round(n * test_size)))
    test_count = min(test_count, n - 1)
    train_count = n - test_count
    if train_count < 1:
        raise ValueError("Недостаточно дней в ряду для разделения")
    return series.iloc[:train_count], series.iloc[train_count:]


def _walk_forward_predict(
    model,
    train_series: pd.Series,
    test_series: pd.Series,
    product_id: int | None = None,
    category_id: int | None = None,
    use_log_target: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Итеративный прогноз тестового периода (как в production forecast)."""
    extended = train_series.copy().astype(float)
    actuals: list[float] = []
    preds: list[float] = []

    for actual in test_series.values:
        forecast_df = prepare_forecast_data(
            extended, horizon=1, product_id=product_id, category_id=category_id
        )
        if forecast_df.empty:
            break
        raw = float(model.predict(forecast_df)[0])
        pred = _prediction_from_raw(raw, use_log_target)
        actuals.append(float(actual))
        preds.append(pred)
        target_date = extended.index.max() + timedelta(days=1)
        extended.loc[target_date] = pred

    return np.array(actuals), np.array(preds)


def _compute_validation_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import (
        mean_absolute_error,
        mean_absolute_percentage_error,
        mean_squared_error,
        r2_score,
    )

    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))

    nonzero = y_true != 0
    if nonzero.any():
        mape = float(mean_absolute_percentage_error(y_true[nonzero], y_pred[nonzero])) * 100.0
    else:
        mape = 0.0

    r2 = float(r2_score(y_true, y_pred)) if len(y_true) >= 2 and np.var(y_true) > 0 else 0.0

    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 2), "r2": round(r2, 4)}


def _validate_global_xgboost(
    products: list,
    demand_map: dict[int, pd.Series],
    test_size: float,
) -> dict[int, dict]:
    """
    Глобальная holdout-валидация: одна модель на train всех SKU, метрики по каждому товару.
    """
    splits: list[tuple] = []
    train_entries: list[tuple[pd.Series, int, int | None]] = []

    for product in products:
        series = demand_map.get(product.id, pd.Series(dtype=float))
        series = _normalize_daily_series(series)
        if len(series) < MIN_VALIDATION_DAYS:
            continue
        train_series, test_series = _chronological_split(series, test_size)
        cid = product.category_id if product.category_id else 0
        splits.append((product.id, train_series, test_series, cid))
        train_entries.append((train_series, product.id, cid))

    if not train_entries:
        return {}

    model, _, _ = _train_global_model(train_entries)
    out: dict[int, dict] = {}

    for pid, train_series, test_series, cid in splits:
        y_true, y_pred = _walk_forward_predict(
            model,
            train_series,
            test_series,
            product_id=pid,
            category_id=cid,
            use_log_target=True,
        )
        if len(y_true) == 0:
            continue
        metrics = _compute_validation_metrics(y_true, y_pred)
        out[pid] = {
            **metrics,
            "train_days": len(train_series),
            "test_days": len(y_true),
            "status": "ok",
        }
    return out


def _aggregate_category_validation(results: list[ValidationMetrics]) -> list[CategoryValidationSummary]:
    by_cat: dict[Optional[int], list[ValidationMetrics]] = {}
    for r in results:
        if r.status != "ok" or r.mae is None:
            continue
        cid = r.category.id if r.category else None
        by_cat.setdefault(cid, []).append(r)

    summaries: list[CategoryValidationSummary] = []
    for cid, rows in by_cat.items():
        cname = rows[0].category.name if rows[0].category else "Без категории"
        summaries.append(CategoryValidationSummary(
            category_id=cid,
            category_name=cname,
            products_count=len(rows),
            products_validated=len(rows),
            avg_mae=round(sum(r.mae for r in rows) / len(rows), 4),
            avg_rmse=round(sum(r.rmse for r in rows) / len(rows), 4),
            avg_mape=round(sum(r.mape for r in rows) / len(rows), 2),
            avg_r2=round(sum(r.r2 for r in rows) / len(rows), 4),
        ))

    return sorted(summaries, key=lambda c: c.category_name)


def _avg_ok_metrics(results: list[ValidationMetrics]) -> dict[str, Optional[float]]:
    ok = [r for r in results if r.status == "ok" and r.mae is not None]
    if not ok:
        return {"avg_mae": None, "avg_rmse": None, "avg_mape": None, "avg_r2": None}
    n = len(ok)
    return {
        "avg_mae": round(sum(r.mae for r in ok) / n, 4),
        "avg_rmse": round(sum(r.rmse for r in ok) / n, 4),
        "avg_mape": round(sum(r.mape for r in ok) / n, 2),
        "avg_r2": round(sum(r.r2 for r in ok) / n, 4),
    }


async def _validate_products_for_method(
    products: list,
    demand_map: dict[int, pd.Series],
    test_size: float,
    method: str,
) -> tuple[list[ValidationMetrics], int, int]:
    min_days = min_days_for_method(method)
    results: list[ValidationMetrics] = []
    validated = 0
    skipped = 0
    loop = asyncio.get_event_loop()

    xgb_cache: dict[int, dict] = {}
    if method == "xgboost":
        xgb_cache = await loop.run_in_executor(
            None, partial(_validate_global_xgboost, products, demand_map, test_size)
        )

    for product in products:
        pid = product.id
        series = demand_map.get(pid, pd.Series(dtype=float))
        category_out = (
            CategoryBrief.model_validate(product.category) if product.category else None
        )
        base = {
            "product_id": pid,
            "product_sku": product.sku,
            "product_name": product.name,
            "category": category_out,
        }

        norm_len = len(_normalize_daily_series(series)) if not series.empty else 0
        if series.empty or norm_len < min_days:
            skipped += 1
            results.append(ValidationMetrics(
                **base,
                status="skipped",
                skip_reason="not_enough_data",
                train_days=norm_len,
            ))
            continue

        try:
            if method == "xgboost":
                out = xgb_cache.get(pid)
                if not out:
                    skipped += 1
                    results.append(ValidationMetrics(
                        **base,
                        status="skipped",
                        skip_reason="not_enough_data",
                        train_days=norm_len,
                    ))
                    continue
            else:
                fn = partial(validate_holdout_statistical, method)
                out = await loop.run_in_executor(None, fn, series, test_size)
            validated += 1
            results.append(ValidationMetrics(**base, **out))
        except ValueError as e:
            skipped += 1
            results.append(ValidationMetrics(
                **base,
                status="skipped",
                skip_reason=str(e),
                train_days=len(_normalize_daily_series(series)),
            ))
        except Exception as e:
            skipped += 1
            logger.warning(f"Валидация product_id={pid} method={method}: {e}")
            results.append(ValidationMetrics(
                **base,
                status="skipped",
                skip_reason="validation_error",
            ))

    return results, validated, skipped


async def _load_validation_products(
    db: AsyncSession,
    product_id: Optional[int],
) -> list:
    from fastapi import HTTPException

    q = (
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.is_active.is_(True))
        .order_by(Product.sku)
    )
    if product_id is not None:
        q = q.where(Product.id == product_id)

    result = await db.execute(q)
    products = result.scalars().all()

    if product_id is not None and not products:
        raise HTTPException(status_code=404, detail="Товар не найден")

    return products


async def run_model_validation(
    db: AsyncSession,
    product_id: Optional[int] = None,
    test_size: float = 0.2,
    forecast_method: str = DEFAULT_METHOD,
) -> ValidateResponse:
    """Holdout-валидация прогноза по завершённым расходам (CONSUMPTION)."""
    from fastapi import HTTPException

    try:
        method = normalize_forecast_method(forecast_method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    products = await _load_validation_products(db, product_id)
    pids = [p.id for p in products]
    demand_map = await _load_demand_series_bulk(db, pids)

    results, validated, skipped = await _validate_products_for_method(
        products, demand_map, test_size, method
    )
    categories = _aggregate_category_validation(results)

    return ValidateResponse(
        validated_at=datetime.now(timezone.utc),
        test_size=test_size,
        forecast_method=method,
        forecast_method_label=_method_label(method),
        products_total=len(products),
        products_validated=validated,
        products_skipped=skipped,
        results=results,
        categories=categories,
    )


async def run_all_methods_validation(
    db: AsyncSession,
    product_id: Optional[int] = None,
    test_size: float = 0.2,
) -> ValidateCompareResponse:
    """Holdout-валидация для всех доступных методов прогноза (одна загрузка истории)."""
    products = await _load_validation_products(db, product_id)
    pids = [p.id for p in products]
    demand_map = await _load_demand_series_bulk(db, pids)

    methods = [m.id for m in list_forecast_methods() if m.available]
    runs: list[MethodValidationRun] = []

    for method in methods:
        results, validated, skipped = await _validate_products_for_method(
            products, demand_map, test_size, method
        )
        avgs = _avg_ok_metrics(results)
        runs.append(MethodValidationRun(
            forecast_method=method,
            forecast_method_label=_method_label(method),
            products_total=len(products),
            products_validated=validated,
            products_skipped=skipped,
            categories=_aggregate_category_validation(results),
            results=results,
            **avgs,
        ))

    runs.sort(
        key=lambda r: (r.avg_mae is None, r.avg_mae if r.avg_mae is not None else float("inf")),
    )

    return ValidateCompareResponse(
        validated_at=datetime.now(timezone.utc),
        test_size=test_size,
        product_id=product_id,
        methods_total=len(runs),
        runs=runs,
    )

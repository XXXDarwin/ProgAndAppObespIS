"""
Статистические методы прогнозирования спроса (без обучения XGBoost на диске).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable, Optional

import numpy as np
import pandas as pd

from app.schemas.ml import ForecastMethodInfo, ForecastPoint

logger = logging.getLogger(__name__)

CONFIDENCE_ALPHA = 1.28
MA_WINDOW = 7
SES_ALPHA = 0.3

# id → (label, описание, min_days, requires_xgb_training)
_METHOD_META: dict[str, tuple[str, str, int, bool]] = {
    "xgboost": (
        "XGBoost (ML)",
        "Градиентный бустинг по лагам и календарю; нужно обучение моделей.",
        42,
        True,
    ),
    "moving_average": (
        "Скользящее среднее",
        f"Средний расход за последние {MA_WINDOW} дней.",
        7,
        False,
    ),
    "exponential_smoothing": (
        "Эксп. сглаживание",
        "Simple Exponential Smoothing (SES), α=0.3.",
        10,
        False,
    ),
    "holt": (
        "Холт (тренд)",
        "Двойное экспоненциальное сглаживание с трендом.",
        14,
        False,
    ),
    "arima": (
        "ARIMA",
        "ARIMA(1,1,1) на дневном ряду спроса.",
        21,
        False,
    ),
}

DEFAULT_METHOD = "xgboost"
_STATSMODELS_OK: Optional[bool] = None


def _statsmodels_available() -> bool:
    global _STATSMODELS_OK
    if _STATSMODELS_OK is None:
        try:
            import statsmodels  # noqa: F401
            _STATSMODELS_OK = True
        except ImportError:
            _STATSMODELS_OK = False
    return _STATSMODELS_OK


def normalize_forecast_method(method: Optional[str]) -> str:
    key = (method or DEFAULT_METHOD).strip().lower()
    if key not in _METHOD_META:
        raise ValueError(f"Неизвестный метод прогноза: {method}")
    if key in ("holt", "arima") and not _statsmodels_available():
        raise ValueError(
            f"Метод «{_METHOD_META[key][0]}» недоступен: не установлен пакет statsmodels"
        )
    return key


def min_days_for_method(method: str) -> int:
    return _METHOD_META[normalize_forecast_method(method)][2]


def method_requires_training(method: str) -> bool:
    return _METHOD_META[normalize_forecast_method(method)][3]


def list_forecast_methods() -> list[ForecastMethodInfo]:
    items: list[ForecastMethodInfo] = []
    for mid, (label, desc, min_days, requires_train) in _METHOD_META.items():
        available = True
        if mid in ("holt", "arima") and not _statsmodels_available():
            available = False
            desc = f"{desc} (требуется statsmodels)"
        items.append(ForecastMethodInfo(
            id=mid,
            label=label,
            description=desc,
            min_history_days=min_days,
            requires_training=requires_train,
            available=available,
        ))
    return items


def normalize_daily_series(series: pd.Series) -> pd.Series:
    series = series.copy()
    series.index = pd.to_datetime(series.index)
    series = series.sort_index()
    if series.empty:
        return series
    full_idx = pd.date_range(series.index.min(), series.index.max(), freq="D")
    return series.reindex(full_idx, fill_value=0).astype(float)


def _recent_residual_std(series: pd.Series, window: int = 14) -> float:
    if len(series) < 2:
        return 1.0
    tail = series.tail(window)
    return float(tail.std()) if tail.std() > 0 else 1.0


def _point(date, pred: float, margin: float) -> ForecastPoint:
    pred = max(0.0, float(pred))
    margin = max(0.0, float(margin))
    return ForecastPoint(
        date=str(date.date()),
        predicted=round(pred, 2),
        lower=round(max(0.0, pred - margin), 2),
        upper=round(pred + margin, 2),
    )


def _forecast_moving_average(series: pd.Series, horizon: int) -> list[ForecastPoint]:
    extended = normalize_daily_series(series)
    margin_base = _recent_residual_std(extended, MA_WINDOW * 2)
    points: list[ForecastPoint] = []

    for _ in range(horizon):
        window = extended.tail(MA_WINDOW)
        pred = float(window.mean()) if len(window) else 0.0
        target_date = extended.index.max() + timedelta(days=1)
        points.append(_point(target_date, pred, CONFIDENCE_ALPHA * margin_base))
        extended.loc[target_date] = pred

    return points


def _forecast_ses(series: pd.Series, horizon: int) -> list[ForecastPoint]:
    extended = normalize_daily_series(series)
    values = extended.values.astype(float)
    level = float(values[0])
    for v in values[1:]:
        level = SES_ALPHA * v + (1 - SES_ALPHA) * level

    margin_base = _recent_residual_std(extended)
    points: list[ForecastPoint] = []

    for _ in range(horizon):
        target_date = extended.index.max() + timedelta(days=1)
        points.append(_point(target_date, level, CONFIDENCE_ALPHA * margin_base))
        extended.loc[target_date] = level

    return points


def _forecast_holt(series: pd.Series, horizon: int) -> list[ForecastPoint]:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    s = normalize_daily_series(series)
    if len(s) < 14:
        raise ValueError("Недостаточно данных для метода Холта (нужно ≥ 14 дней)")

    model = ExponentialSmoothing(
        s.values,
        trend="add",
        seasonal=None,
        initialization_method="estimated",
    )
    fitted = model.fit(optimized=True)
    preds = np.maximum(fitted.forecast(horizon), 0.0)
    margin = CONFIDENCE_ALPHA * _recent_residual_std(s)
    points: list[ForecastPoint] = []
    last_date = s.index.max()

    for i, pred in enumerate(preds):
        target_date = last_date + timedelta(days=i + 1)
        points.append(_point(target_date, float(pred), margin))

    return points


def _forecast_arima(series: pd.Series, horizon: int) -> list[ForecastPoint]:
    from statsmodels.tsa.arima.model import ARIMA

    s = normalize_daily_series(series)
    if len(s) < 21:
        raise ValueError("Недостаточно данных для ARIMA (нужно ≥ 21 день)")

    try:
        fitted = ARIMA(s.values, order=(1, 1, 1)).fit()
        preds = np.maximum(fitted.forecast(steps=horizon), 0.0)
    except Exception as e:
        logger.warning(f"ARIMA fit failed, fallback to SES: {e}")
        return _forecast_ses(series, horizon)

    margin = CONFIDENCE_ALPHA * _recent_residual_std(s)
    points: list[ForecastPoint] = []
    last_date = s.index.max()

    for i, pred in enumerate(preds):
        target_date = last_date + timedelta(days=i + 1)
        points.append(_point(target_date, float(pred), margin))

    return points


_STAT_FORECASTERS: dict[str, Callable[[pd.Series, int], list[ForecastPoint]]] = {
    "moving_average": _forecast_moving_average,
    "exponential_smoothing": _forecast_ses,
    "holt": _forecast_holt,
    "arima": _forecast_arima,
}


def forecast_statistical(method: str, series: pd.Series, horizon: int) -> list[ForecastPoint]:
    """Прогноз на horizon дней вперёд статистическим методом."""
    method = normalize_forecast_method(method)
    if method == "xgboost":
        raise ValueError("Для xgboost используйте ml_service.generate_forecast")

    fn = _STAT_FORECASTERS.get(method)
    if not fn:
        raise ValueError(f"Метод не реализован: {method}")

    s = normalize_daily_series(series)
    if len(s) < min_days_for_method(method):
        raise ValueError(
            f"Недостаточно истории: {len(s)} дн. (нужно ≥ {min_days_for_method(method)})"
        )
    return fn(s, horizon)


def _walk_forward_statistical(
    method: str,
    train_series: pd.Series,
    test_series: pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    """Пошаговый прогноз на тесте (для MA, SES)."""
    extended = normalize_daily_series(train_series)
    test = normalize_daily_series(test_series)
    actuals: list[float] = []
    preds: list[float] = []

    for actual in test.values:
        one = forecast_statistical(method, extended, horizon=1)
        if not one:
            break
        pred = one[0].predicted
        actuals.append(float(actual))
        preds.append(pred)
        target_date = extended.index.max() + timedelta(days=1)
        extended.loc[target_date] = pred

    return np.array(actuals), np.array(preds)


def _holdout_multistep(
    method: str,
    train_series: pd.Series,
    test_series: pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    """Многошаговый прогноз с одного обучения (Holt, ARIMA)."""
    test = normalize_daily_series(test_series)
    points = forecast_statistical(method, train_series, horizon=len(test))
    preds = np.array([p.predicted for p in points[: len(test)]])
    actuals = test.values.astype(float)[: len(preds)]
    return actuals, preds


def _chronological_split(series: pd.Series, test_size: float) -> tuple[pd.Series, pd.Series]:
    series = normalize_daily_series(series)
    n = len(series)
    test_count = max(1, int(round(n * test_size)))
    test_count = min(test_count, n - 1)
    train_count = n - test_count
    if train_count < 1:
        raise ValueError("Недостаточно дней в ряду для разделения")
    return series.iloc[:train_count], series.iloc[train_count:]


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


def validate_holdout_statistical(
    method: str,
    series: pd.Series,
    test_size: float,
) -> dict:
    """Holdout-валидация для статистического метода."""
    method = normalize_forecast_method(method)
    series = normalize_daily_series(series)
    min_days = min_days_for_method(method)

    if len(series) < min_days:
        raise ValueError(f"Недостаточно истории: {len(series)} дн. (нужно ≥ {min_days})")

    train_series, test_series = _chronological_split(series, test_size)
    if len(test_series) < 1:
        raise ValueError("Пустая тестовая выборка")

    if method in ("holt", "arima"):
        y_true, y_pred = _holdout_multistep(method, train_series, test_series)
    else:
        y_true, y_pred = _walk_forward_statistical(method, train_series, test_series)

    if len(y_true) == 0:
        raise ValueError("Не удалось сформировать прогнозы на тестовой выборке")

    metrics = _compute_validation_metrics(y_true, y_pred)
    return {
        **metrics,
        "train_days": len(train_series),
        "test_days": len(y_true),
        "status": "ok",
    }

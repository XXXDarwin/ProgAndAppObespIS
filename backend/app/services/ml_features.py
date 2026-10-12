"""
Feature Engineering для прогнозирования спроса.

Входные данные: временной ряд daily_demand (дата → кол-во).
Выходные данные: DataFrame с признаками для XGBoost.
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta


# Российские праздники (статический список основных дат)
RU_HOLIDAYS = {
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),  # Новый год
    (2, 23),   # День защитника
    (3, 8),    # 8 марта
    (5, 1),    # Праздник труда
    (5, 9),    # День Победы
    (6, 12),   # День России
    (11, 4),   # День народного единства
}


def is_holiday(dt: date) -> int:
    return int((dt.month, dt.day) in RU_HOLIDAYS)


def transform_target(y: pd.Series) -> pd.Series:
    """log(1+y) — сглаживает редкие крупные отгрузки."""
    return np.log1p(y.astype(float))


def inverse_transform_target(y_pred: np.ndarray | pd.Series) -> np.ndarray:
    """Обратное преобразование прогноза."""
    return np.maximum(0.0, np.expm1(np.asarray(y_pred, dtype=float)))


def build_features(
    series: pd.Series,
    horizon: int = 0,
    product_id: int | None = None,
    category_id: int | None = None,
) -> pd.DataFrame:
    """
    Строит матрицу признаков из временного ряда.

    series: pd.Series с DatetimeIndex и значениями спроса.
    horizon: если > 0, добавляет строки для прогноза (без target).
    product_id / category_id: для глобальной модели по каталогу.
    """
    series = series.copy()
    series.index = pd.to_datetime(series.index)
    series = series.sort_index()

    full_idx = pd.date_range(series.index.min(), series.index.max(), freq="D")
    series = series.reindex(full_idx, fill_value=0)

    if horizon > 0:
        future_idx = pd.date_range(
            series.index.max() + timedelta(days=1),
            periods=horizon,
            freq="D",
        )
        future = pd.Series(np.nan, index=future_idx)
        series = pd.concat([series, future])

    df = pd.DataFrame({"y": series})
    df.index.name = "date"

    shifted = df["y"].shift(1)

    for lag in [1, 7, 14, 21, 28]:
        df[f"lag_{lag}"] = df["y"].shift(lag)

    for window in [7, 14, 28]:
        df[f"ma_{window}"] = shifted.rolling(window, min_periods=1).mean()
        df[f"std_{window}"] = shifted.rolling(window, min_periods=1).std().fillna(0)
        df[f"median_{window}"] = shifted.rolling(window, min_periods=1).median()

    df["day_of_week"] = df.index.dayofweek
    df["month"] = df.index.month
    df["week_of_year"] = df.index.isocalendar().week.astype(int)
    df["is_weekend"] = (df.index.dayofweek >= 5).astype(int)
    df["is_holiday"] = [is_holiday(d.date()) for d in df.index]
    df["is_friday"] = (df.index.dayofweek == 4).astype(int)
    df["trend"] = np.arange(len(df))

    if product_id is not None:
        df["product_id"] = int(product_id)
    if category_id is not None:
        df["category_id"] = int(category_id)

    return df


BASE_FEATURE_COLS = [
    "lag_1", "lag_7", "lag_14", "lag_21", "lag_28",
    "ma_7", "ma_14", "ma_28",
    "std_7", "std_14", "std_28",
    "median_7", "median_14",
    "day_of_week", "month", "week_of_year",
    "is_weekend", "is_holiday", "is_friday", "trend",
]

ENTITY_FEATURE_COLS = ["product_id", "category_id"]

FEATURE_COLS = BASE_FEATURE_COLS + ENTITY_FEATURE_COLS


def _feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in FEATURE_COLS if c in df.columns]


def prepare_train_data(
    series: pd.Series,
    product_id: int | None = None,
    category_id: int | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """(X, y) для обучения — только строки с полным набором лагов."""
    df = build_features(series, horizon=0, product_id=product_id, category_id=category_id)
    df = df.dropna()
    cols = _feature_columns(df)
    return df[cols], df["y"]


def prepare_forecast_data(
    series: pd.Series,
    horizon: int,
    product_id: int | None = None,
    category_id: int | None = None,
) -> pd.DataFrame:
    """Признаки для строк прогноза (y = NaN)."""
    df = build_features(series, horizon=horizon, product_id=product_id, category_id=category_id)
    cols = _feature_columns(df)
    return df[df["y"].isna()][cols]

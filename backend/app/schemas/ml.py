from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


class CategoryBrief(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


# ─── Training ─────────────────────────────────────────────────────────────────

class TrainRequest(BaseModel):
    product_ids: Optional[List[int]] = None   # None = все (или по category_id)
    category_id: Optional[int] = None         # обучить только товары категории
    force: bool = False                        # переобучить даже если модель актуальна


class TrainStatus(BaseModel):
    status: str                    # idle | running | done | error
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    products_trained: int = 0
    error: Optional[str] = None


# ─── Forecast ─────────────────────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    product_id: int
    days: int = 14                 # горизонт прогноза: 7–30 дней

    @classmethod
    def validate_days(cls, v: int) -> int:
        return max(7, min(30, v))


class ForecastPoint(BaseModel):
    date: str                      # "2024-06-01"
    predicted: float
    lower: float
    upper: float


class ForecastInsight(BaseModel):
    """Сводка для закупок: остаток vs прогноз спроса."""
    total_stock: int
    avg_daily_demand_14d: float
    forecast_total: float
    forecast_avg_daily: float
    days_until_stockout: Optional[float] = None
    recommendation: str


class ForecastMethodInfo(BaseModel):
    id: str
    label: str
    description: str
    min_history_days: int
    requires_training: bool = False
    available: bool = True


class ForecastResponse(BaseModel):
    product_id: int
    product_sku: str
    product_name: str
    category: Optional[CategoryBrief] = None
    horizon_days: int
    forecast_method: str = "xgboost"
    forecast_method_label: Optional[str] = None
    model_version: Optional[str]
    generated_at: datetime
    data_points_total: int = 0
    forecast: List[ForecastPoint]
    history: List[ForecastPoint]   # фактические данные за последние 60 дней
    insights: Optional[ForecastInsight] = None


# ─── History import (для ML) ──────────────────────────────────────────────────

class DemandHistoryRecord(BaseModel):
    sku: str
    date: date
    quantity: int

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity должно быть > 0")
        return v


class DemandHistoryImport(BaseModel):
    comment: Optional[str] = "Синтетическая история спроса"
    records: List[DemandHistoryRecord]


class DemandHistoryImportResult(BaseModel):
    orders_created: int
    items_created: int
    days_covered: int
    skus: int


# ─── Model info ───────────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    product_id: int
    product_sku: str
    product_name: Optional[str] = None
    category: Optional[CategoryBrief] = None
    total_stock: int = 0
    history_days: int = 0
    trained_at: Optional[datetime] = None
    model_version: Optional[str] = None
    data_points: int = 0
    ready: bool = False
    can_train: bool = False


class CategoryModelSummary(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    products_count: int
    models_ready: int
    history_ready: int


class ForecastOverview(BaseModel):
    total_products: int
    models_ready: int
    models_pending: int
    history_ready: int
    training_status: str
    products_trained_last_run: int = 0
    categories: List[CategoryModelSummary] = []


# ─── Model validation (holdout) ─────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    product_id: Optional[int] = None
    test_size: float = 0.2
    forecast_method: str = "xgboost"

    @field_validator("test_size")
    @classmethod
    def clamp_test_size(cls, v: float) -> float:
        return max(0.1, min(0.4, v))


class ValidationMetrics(BaseModel):
    product_id: int
    product_sku: str
    product_name: Optional[str] = None
    category: Optional[CategoryBrief] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    r2: Optional[float] = None
    train_days: int = 0
    test_days: int = 0
    status: str = "ok"
    skip_reason: Optional[str] = None


class CategoryValidationSummary(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    products_count: int
    products_validated: int
    avg_mae: Optional[float] = None
    avg_rmse: Optional[float] = None
    avg_mape: Optional[float] = None
    avg_r2: Optional[float] = None


class ValidateResponse(BaseModel):
    validated_at: datetime
    test_size: float
    forecast_method: str = "xgboost"
    forecast_method_label: Optional[str] = None
    products_total: int
    products_validated: int
    products_skipped: int
    results: List[ValidationMetrics]
    categories: List[CategoryValidationSummary] = []


class ValidateCompareRequest(BaseModel):
    product_id: Optional[int] = None
    test_size: float = 0.2

    @field_validator("test_size")
    @classmethod
    def clamp_test_size_compare(cls, v: float) -> float:
        return max(0.1, min(0.4, v))


class MethodValidationRun(BaseModel):
    forecast_method: str
    forecast_method_label: Optional[str] = None
    products_total: int
    products_validated: int
    products_skipped: int
    avg_mae: Optional[float] = None
    avg_rmse: Optional[float] = None
    avg_mape: Optional[float] = None
    avg_r2: Optional[float] = None
    categories: List[CategoryValidationSummary] = []
    results: List[ValidationMetrics] = []


class ValidateCompareResponse(BaseModel):
    validated_at: datetime
    test_size: float
    product_id: Optional[int] = None
    methods_total: int
    runs: List[MethodValidationRun]

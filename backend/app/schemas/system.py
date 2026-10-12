from pydantic import BaseModel, Field


class WarehouseResetRequest(BaseModel):
    delete_users: bool = Field(
        False,
        description="Удалить всех пользователей, кроме администраторов (и текущего админа)",
    )


class WarehouseResetResult(BaseModel):
    detail: str
    users_removed: int = 0
    orders_removed: int = 0
    order_items_removed: int = 0
    inventory_tasks_removed: int = 0
    stocks_removed: int = 0
    products_removed: int = 0
    categories_removed: int = 0
    cells_removed: int = 0
    predictions_removed: int = 0
    audit_logs_removed: int = 0
    ml_models_removed: int = 0

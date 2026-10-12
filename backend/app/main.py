from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import AsyncSessionLocal, engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Регистрируем все модели до create_all (в т.ч. inventory_tasks)
    import app.models.models  # noqa: F401

    # Создаём таблицы (dev-режим; в проде — alembic upgrade head)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Создаём администратора по умолчанию если БД пустая
    async with AsyncSessionLocal() as db:
        from app.services.auth_service import AuthService
        await AuthService.ensure_admin_exists(db)

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Роутеры ──────────────────────────────────────────────────────────────────

from app.api import auth, products, cells, warehouse, predictions  # noqa: E402

app.include_router(auth.router,        prefix="/api/auth",        tags=["Авторизация"])
app.include_router(products.router,    prefix="/api/products",    tags=["Товары"])
app.include_router(cells.router,       prefix="/api/cells",       tags=["Ячейки"])
app.include_router(warehouse.router,   prefix="/api/warehouse",   tags=["Склад"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["Прогнозирование"])


# ─── Системные эндпоинты ──────────────────────────────────────────────────────

@app.get("/api/health", tags=["Система"])
async def health_check():
    return {"status": "ok", "version": settings.VERSION}

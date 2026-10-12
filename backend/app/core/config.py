from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://wms_user:wms_pass@db:5432/wms_db"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://wms_user:wms_pass@db:5432/wms_db"

    # JWT
    SECRET_KEY: str = "change-me-in-production-use-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # App
    PROJECT_NAME: str = "WMS — Система управления складом"
    VERSION: str = "1.0.0"
    # Через запятую; генератор данных: http://localhost:8765
    CORS_ORIGINS: str = (
        "http://localhost:5173,"
        "http://localhost:80,"
        "http://localhost,"
        "http://127.0.0.1,"
        "http://localhost:8765,"
        "http://127.0.0.1:8765"
    )

    class Config:
        env_file = ".env"


settings = Settings()

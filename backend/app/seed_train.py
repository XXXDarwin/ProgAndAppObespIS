"""
Запускает обучение ML-моделей после seed.
Использование: docker compose exec backend python -m app.seed_train
"""
import asyncio
from app.services.ml_service import run_training_task


async def main():
    print("🤖 Запускаем обучение ML-моделей для всех товаров...")
    print("   Это займёт ~1-2 минуты...\n")
    await run_training_task(product_ids=None, force=True)
    print("\n✅ Обучение завершено! Прогноз доступен в разделе «Прогнозирование».")


if __name__ == "__main__":
    asyncio.run(main())

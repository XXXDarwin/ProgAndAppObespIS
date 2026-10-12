"""
Скрипт начального заполнения БД демо-данными.
Запускать: docker compose exec backend python -m app.seed
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.database import AsyncSessionLocal, engine, Base
from app.models.models import (
    Category, Product, StorageCell, Stock,
    Order, OrderItem, OrderType, OrderStatus,
    User, UserRole, AuditLog,
)
from app.core.security import hash_password


# ─── Demo data ────────────────────────────────────────────────────────────────

CATEGORIES = ["Электроника", "Хозтовары", "Одежда", "Продукты питания", "Инструменты"]

PRODUCTS = [
    ("SKU-001", "Ноутбук Lenovo IdeaPad",        "Электроника",       2.1,  "шт"),
    ("SKU-002", "Мышь беспроводная Logitech",     "Электроника",       0.1,  "шт"),
    ("SKU-003", "Клавиатура механическая",        "Электроника",       0.8,  "шт"),
    ("SKU-004", "Монитор 27\" Samsung",           "Электроника",       4.5,  "шт"),
    ("SKU-005", "Наушники Sony WH-1000XM5",      "Электроника",       0.25, "шт"),
    ("SKU-006", "Швабра телескопическая",         "Хозтовары",         0.5,  "шт"),
    ("SKU-007", "Моющее средство Fairy 5л",       "Хозтовары",         5.2,  "шт"),
    ("SKU-008", "Перчатки резиновые (пара)",      "Хозтовары",         0.1,  "пара"),
    ("SKU-009", "Футболка хлопок M",              "Одежда",            0.2,  "шт"),
    ("SKU-010", "Джинсы классика L",              "Одежда",            0.5,  "шт"),
    ("SKU-011", "Носки (упак. 5 пар)",            "Одежда",            0.15, "упак"),
    ("SKU-012", "Сахар 1кг",                      "Продукты питания",  1.0,  "кг"),
    ("SKU-013", "Мука пшеничная 2кг",             "Продукты питания",  2.0,  "кг"),
    ("SKU-014", "Масло подсолнечное 1л",          "Продукты питания",  0.9,  "шт"),
    ("SKU-015", "Шуруповёрт Bosch",               "Инструменты",       1.8,  "шт"),
    ("SKU-016", "Набор отвёрток 12 шт",           "Инструменты",       0.6,  "шт"),
    ("SKU-017", "Рулетка 5м",                     "Инструменты",       0.2,  "шт"),
    ("SKU-018", "Кабель USB-C 2м",                "Электроника",       0.05, "шт"),
    ("SKU-019", "Чехол для ноутбука 15\"",        "Электроника",       0.3,  "шт"),
    ("SKU-020", "Удлинитель 5 розеток 3м",        "Хозтовары",         0.7,  "шт"),
]

USERS = [
    ("manager1", "Иванов Пётр Сергеевич",   UserRole.MANAGER, "manager123"),
    ("worker1",  "Смирнов Алексей Игоревич", UserRole.WORKER,  "worker123"),
    ("worker2",  "Козлова Мария Дмитриевна", UserRole.WORKER,  "worker123"),
]


async def seed():
    print("🌱 Начинаем заполнение БД демо-данными...\n")

    async with AsyncSessionLocal() as db:

        # ── Categories ────────────────────────────────────────────────────────
        cat_map = {}
        for cat_name in CATEGORIES:
            existing = await db.execute(select(Category).where(Category.name == cat_name))
            cat = existing.scalar_one_or_none()
            if not cat:
                cat = Category(name=cat_name)
                db.add(cat)
                await db.flush()
            cat_map[cat_name] = cat
        await db.commit()
        print(f"✅ Категории: {len(CATEGORIES)} шт.")

        # ── Products ──────────────────────────────────────────────────────────
        product_map = {}
        created_products = 0
        for sku, name, cat_name, weight, unit in PRODUCTS:
            existing = await db.execute(select(Product).where(Product.sku == sku))
            product = existing.scalar_one_or_none()
            if not product:
                product = Product(
                    sku=sku, name=name,
                    category_id=cat_map[cat_name].id,
                    weight=weight, unit=unit,
                )
                db.add(product)
                await db.flush()
                created_products += 1
            product_map[sku] = product
        await db.commit()
        print(f"✅ Товары: {created_products} создано, {len(PRODUCTS) - created_products} уже было.")

        # ── Storage Cells ─────────────────────────────────────────────────────
        zones = ["A", "B", "C"]
        cell_list = []
        created_cells = 0
        for zone in zones:
            for rack in range(1, 5):       # 4 стеллажа
                for shelf in range(1, 4):  # 3 полки
                    for pos in range(1, 6): # 5 позиций
                        existing = await db.execute(
                            select(StorageCell).where(
                                StorageCell.zone == zone,
                                StorageCell.rack == rack,
                                StorageCell.shelf == shelf,
                                StorageCell.position == pos,
                            )
                        )
                        cell = existing.scalar_one_or_none()
                        if not cell:
                            cell = StorageCell(zone=zone, rack=rack, shelf=shelf,
                                               position=pos, max_capacity=100)
                            db.add(cell)
                            await db.flush()
                            created_cells += 1
                        cell_list.append(cell)
        await db.commit()
        print(f"✅ Ячейки: {created_cells} создано ({len(zones)} зоны × 4 стеллажа × 3 полки × 5 позиций = {len(zones)*4*3*5})")

        # ── Users ─────────────────────────────────────────────────────────────
        created_users = 0
        user_list = []
        for username, full_name, role, password in USERS:
            existing = await db.execute(select(User).where(User.username == username))
            user = existing.scalar_one_or_none()
            if not user:
                user = User(username=username, full_name=full_name, role=role,
                            password_hash=hash_password(password))
                db.add(user)
                created_users += 1
            user_list.append(user)
        await db.commit()
        print(f"✅ Пользователи: {created_users} создано.")

        # Получаем admin для аудита
        admin_res = await db.execute(select(User).where(User.username == "admin"))
        admin = admin_res.scalar_one_or_none()

        # ── Arrivals: начальные остатки ───────────────────────────────────────
        products_list = list(product_map.values())
        arrival_order = Order(
            type=OrderType.ARRIVAL,
            status=OrderStatus.COMPLETED,
            created_by=admin.id if admin else None,
            comment="Начальное заполнение склада",
            closed_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        db.add(arrival_order)
        await db.flush()

        cell_idx = 0
        for product in products_list:
            # Проверяем что остатка ещё нет
            existing_stock = await db.execute(
                select(Stock).where(Stock.product_id == product.id)
            )
            if existing_stock.scalar_one_or_none():
                continue

            qty = random.randint(20, 150)
            cell = cell_list[cell_idx % len(cell_list)]
            cell_idx += 1

            oi = OrderItem(order_id=arrival_order.id, product_id=product.id,
                           cell_id=cell.id, quantity=qty)
            db.add(oi)

            stock = Stock(product_id=product.id, cell_id=cell.id, quantity=qty)
            db.add(stock)

        await db.commit()
        print(f"✅ Начальные остатки: {len(products_list)} товаров размещены на складе.")

        # ── Historical consumption orders (для ML) ────────────────────────────
        print("📊 Генерируем историю расходов (90 дней) для ML-обучения...")
        worker = user_list[1] if len(user_list) > 1 else admin

        consumption_count = 0
        for days_ago in range(89, 0, -1):
            dt = datetime.now(timezone.utc) - timedelta(days=days_ago)

            # 0–3 заказа в день
            n_orders = random.choices([0, 1, 2, 3], weights=[20, 40, 30, 10])[0]
            for _ in range(n_orders):
                # Выбираем 1–4 товара
                order_products = random.sample(products_list, k=random.randint(1, 4))
                order = Order(
                    type=OrderType.CONSUMPTION,
                    status=OrderStatus.COMPLETED,
                    created_by=worker.id if worker else None,
                    comment=f"Расход (демо-данные, день -{days_ago})",
                    created_at=dt,
                    closed_at=dt + timedelta(hours=random.randint(1, 4)),
                )
                db.add(order)
                await db.flush()

                for product in order_products:
                    # Берём из остатков
                    stock_res = await db.execute(
                        select(Stock)
                        .where(Stock.product_id == product.id, Stock.quantity > 0)
                        .limit(1)
                    )
                    stock = stock_res.scalar_one_or_none()
                    if not stock:
                        continue

                    take = min(stock.quantity, random.randint(1, 5))
                    stock.quantity -= take

                    db.add(OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        cell_id=stock.cell_id,
                        quantity=take,
                    ))
                consumption_count += 1

        await db.commit()
        print(f"✅ Исторических заказов расхода: {consumption_count} шт. (за 90 дней)")

        print("\n🎉 Заполнение завершено!")
        print("\n📋 Учётные данные для входа:")
        print("   admin    / admin123   → Администратор")
        print("   manager1 / manager123 → Менеджер")
        print("   worker1  / worker123  → Кладовщик")
        print("   worker2  / worker123  → Кладовщик")
        print("\n   Для ML: docker compose exec backend python -m app.seed_train")


if __name__ == "__main__":
    asyncio.run(seed())

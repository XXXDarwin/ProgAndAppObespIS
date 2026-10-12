#!/usr/bin/env python3
"""
CLI-генератор файлов для WMS (альтернатива веб-приложению).

Примеры:
  python generate.py products -n 20 -o products.xlsx
  python generate.py arrival -n 10 -o arrival.json --demo-catalog
  python generate.py consumption -n 8 -o consumption.csv --demo-catalog
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import pandas as pd

DEMO_PRODUCTS = [
    {"sku": "SKU-001", "name": "Ноутбук Lenovo IdeaPad", "category": "Электроника", "unit": "шт", "weight": 2.1},
    {"sku": "SKU-002", "name": "Мышь беспроводная Logitech", "category": "Электроника", "unit": "шт", "weight": 0.1},
    {"sku": "SKU-003", "name": "Клавиатура механическая", "category": "Электроника", "unit": "шт", "weight": 0.8},
    {"sku": "SKU-004", "name": "Монитор 27\" Samsung", "category": "Электроника", "unit": "шт", "weight": 4.5},
    {"sku": "SKU-005", "name": "Наушники Sony WH-1000XM5", "category": "Электроника", "unit": "шт", "weight": 0.25},
    {"sku": "SKU-006", "name": "Швабра телескопическая", "category": "Хозтовары", "unit": "шт", "weight": 0.5},
    {"sku": "SKU-007", "name": "Моющее средство Fairy 5л", "category": "Хозтовары", "unit": "шт", "weight": 5.2},
    {"sku": "SKU-008", "name": "Перчатки резиновые (пара)", "category": "Хозтовары", "unit": "пара", "weight": 0.1},
    {"sku": "SKU-009", "name": "Футболка хлопок M", "category": "Одежда", "unit": "шт", "weight": 0.2},
    {"sku": "SKU-010", "name": "Джинсы классика L", "category": "Одежда", "unit": "шт", "weight": 0.5},
]

CATEGORIES = ["Электроника", "Хозтовары", "Одежда", "Продукты питания", "Инструменты"]
NAMES = ["Адаптер питания", "Блокнот А4", "Степлер", "Маркер", "Скотч", "Папка", "Лампа"]


def random_cell() -> str:
    z = random.choice("ABC")
    return f"{z}{random.randint(1, 3)}-{random.randint(1, 3)}-{random.randint(1, 3)}"


def gen_products(n: int, prefix: str, demo: bool) -> list[dict]:
    if demo:
        return [dict(p) for p in DEMO_PRODUCTS[:n]]
    out = []
    for i in range(1, n + 1):
        sku = f"{prefix}-{i:03d}"
        out.append({
            "sku": sku,
            "name": f"{random.choice(NAMES)} {sku}",
            "unit": "шт",
            "category": CATEGORIES[i % len(CATEGORIES)],
            "weight": round(random.uniform(0.1, 5), 2),
            "description": f"Generated {sku}",
        })
    return out


def gen_order(catalog: list[dict], n: int, qmin: int, qmax: int, cells: bool) -> list[dict]:
    pool = catalog.copy()
    random.shuffle(pool)
    lines = []
    for p in pool[:n]:
        row = {"sku": p["sku"], "quantity": random.randint(qmin, qmax)}
        if cells:
            row["cell"] = random_cell()
        lines.append(row)
    return lines


def save(rows: list[dict], path: Path, comment: str | None, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()

    if kind in ("arrival", "consumption"):
        payload = {
            "comment": comment or f"Generated {kind}",
            "items": [
                {"sku": r["sku"], "quantity": r["quantity"], **(
                    {"cell_address": r["cell"]} if r.get("cell") else {}
                )}
                for r in rows
            ],
        }
        if ext == ".json":
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            df = pd.DataFrame(rows)
            if ext == ".csv":
                df.to_csv(path, index=False)
            else:
                df.to_excel(path, index=False)
        return

    payload = {"skip_duplicates": True, "items": rows}
    if ext == ".json":
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        df = pd.DataFrame(rows)
        if ext == ".csv":
            df.to_csv(path, index=False)
        else:
            df.to_excel(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="WMS data file generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prod = sub.add_parser("products", help="Generate product catalog")
    p_prod.add_argument("-n", "--count", type=int, default=20)
    p_prod.add_argument("--prefix", default="GEN")
    p_prod.add_argument("--demo-catalog", action="store_true")
    p_prod.add_argument("-o", "--output", type=Path, default=Path("products.xlsx"))

    for name in ("arrival", "consumption"):
        p = sub.add_parser(name, help=f"Generate {name} order file")
        p.add_argument("-n", "--lines", type=int, default=8)
        p.add_argument("--qty-min", type=int, default=1)
        p.add_argument("--qty-max", type=int, default=20)
        p.add_argument("--cells", action="store_true")
        p.add_argument("--comment", default="")
        p.add_argument("--catalog", type=Path, help="JSON/XLSX with products (sku column)")
        p.add_argument("--demo-catalog", action="store_true")
        p.add_argument("-o", "--output", type=Path, default=Path(f"{name}.json"))

    args = parser.parse_args()

    if args.cmd == "products":
        rows = gen_products(args.count, args.prefix, args.demo_catalog)
        save(rows, args.output, None, "products")
        print(f"OK: {len(rows)} products -> {args.output}")
        return

    if args.demo_catalog:
        catalog = DEMO_PRODUCTS
    elif args.catalog:
        if args.catalog.suffix.lower() == ".json":
            data = json.loads(args.catalog.read_text(encoding="utf-8"))
            catalog = data.get("items", data)
        else:
            catalog = pd.read_excel(args.catalog).to_dict("records")
    else:
        catalog = DEMO_PRODUCTS

    rows = gen_order(catalog, args.lines, args.qty_min, args.qty_max, args.cells)
    save(rows, args.output, args.comment or None, args.cmd)
    print(f"OK: {len(rows)} lines -> {args.output}")


if __name__ == "__main__":
    main()

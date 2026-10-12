#!/usr/bin/env python3

"""CLI: генерация файла истории спроса для WMS ML (расширенные параметры)."""

import argparse

import json

import math

import random

from datetime import date, timedelta

from pathlib import Path



import pandas as pd



RU_HOLIDAYS = {

    (1, d) for d in range(1, 9)

} | {(2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4)}



WEEKDAY_DEFAULT = [1.05, 1.1, 1.08, 1.05, 1.0, 0.92, 0.88]



PRESETS = {

    "stable": dict(mean=15, trend=0, noise=15, weekend=0.85, holiday=0.7, monthly=0.1, zero=0.05,

                  spike=0, drop=0, outlier=0, autocorr=0, trend_break=0, sku_lo=0.75, sku_hi=1.25),

    "ml_benchmark": dict(mean=16, trend=0.04, noise=30, weekend=0.82, holiday=0.72, monthly=0.18, zero=0.07,

                         spike=0.05, drop=0.04, outlier=0.02, autocorr=0.45, trend_break=0.2, sku_lo=0.3, sku_hi=2.0),

    "irregular": dict(mean=14, trend=0.03, noise=35, weekend=0.75, holiday=0.65, monthly=0.22, zero=0.1,

                     spike=0.08, drop=0.06, outlier=0.025, autocorr=0.4, trend_break=0.25, sku_lo=0.25, sku_hi=2.2),

    "volatile": dict(mean=18, trend=0, noise=45, weekend=1, holiday=1, monthly=0.2, zero=0.08,

                     spike=0.06, drop=0.05, outlier=0.02, autocorr=0.35, trend_break=0.12, sku_lo=0.35, sku_hi=2.0),

    "ml_benchmark_super": dict(mean=15, trend=0.035, noise=33, weekend=0.78, holiday=0.68, monthly=0.21, zero=0.09,

                             spike=0.1, drop=0.055, outlier=0.032, autocorr=0.43, trend_break=0.22, sku_lo=0.22, sku_hi=2.4),

    "xgboost_wins": dict(mean=14, trend=0.05, noise=22, weekend=0.7, holiday=0.65, monthly=0.34, zero=0.04,

                         spike=0.04, drop=0.02, outlier=0.015, autocorr=0.58, trend_break=0.12, sku_lo=0.4, sku_hi=1.8,

                         friday=1.35, september=1.5, days_default=900),

}

XGBOOST_WINS_WEEKDAY = [1.02, 1.04, 1.03, 1.02, 1.28, 0.78, 0.72]





def is_holiday(d: date) -> bool:

    return (d.month, d.day) in RU_HOLIDAYS





def pick_trend_break(days: int, chance: float):

    if chance <= 0 or days < 30:

        return None

    if random.random() >= chance:

        return None

    margin = int(days * 0.15)

    return margin + random.randint(0, max(0, days - 2 * margin - 1))





def gen_series(

    days: int,

    start: date,

    mean: float,

    trend: float,

    noise_pct: float,

    weekend: float,

    holiday: float,

    monthly: float,

    weekday,

    zero_chance: float,

    spike_chance: float = 0,

    spike_mult: float = 2.5,

    drop_chance: float = 0,

    drop_mult: float = 0.4,

    outlier_chance: float = 0,

    outlier_mult: float = 4,

    autocorr: float = 0,

    trend_break_chance: float = 0,

    trend_break_jitter: float = 0.6,

    friday_boost: float = 1.0,

    september_boost: float = 1.0,

) -> list[dict]:

    ac = max(0.0, min(0.95, autocorr))

    innov_scale = math.sqrt(max(0.05, 1 - ac * ac))

    break_day = pick_trend_break(days, trend_break_chance)

    ar_shock = 0.0

    trend_factor = 1.0

    rows = []



    for t in range(days):

        d = start + timedelta(days=t)

        dow = d.weekday()



        if break_day is not None and t == break_day:

            trend_factor *= 1 + (random.random() * 2 - 1) * trend_break_jitter



        if random.random() < zero_chance:

            ar_shock *= ac

            continue



        v = mean + trend * trend_factor * t

        v *= weekday[dow]

        if dow >= 5:

            v *= weekend

        if is_holiday(d):

            v *= holiday

        if monthly > 0:

            v *= 1 + monthly * math.sin(2 * math.pi * t / 30.4)

        if dow == 4 and friday_boost > 1:

            v *= friday_boost

        if d.month == 9 and september_boost > 1:

            v *= september_boost



        ar_shock = ac * ar_shock + innov_scale * random.gauss(0, 1)

        v += (noise_pct / 100) * mean * ar_shock



        if spike_chance > 0 and random.random() < spike_chance:

            v *= spike_mult

        if drop_chance > 0 and random.random() < drop_chance:

            v *= drop_mult

        if outlier_chance > 0 and random.random() < outlier_chance:

            v = mean * outlier_mult * (0.8 + random.random() * 0.4)



        v = max(0, int(round(v)))

        if v > 0:

            rows.append({"date": d.isoformat(), "quantity": v})

    return rows





def main():

    p = argparse.ArgumentParser(

        description="Generate demand history for WMS ML",

        formatter_class=argparse.ArgumentDefaultsHelpFormatter,

    )

    p.add_argument("-n", "--days", type=int, default=365)

    p.add_argument("--preset", choices=sorted(PRESETS.keys()), default="ml_benchmark_super")

    p.add_argument("--mean", type=float, help="override preset base mean")

    p.add_argument("--trend", type=float, help="override trend per day")

    p.add_argument("--noise", type=float, help="noise %% of mean")

    p.add_argument("--weekend", type=float)

    p.add_argument("--holiday", type=float)

    p.add_argument("--monthly", type=float)

    p.add_argument("--zero", type=float, help="zero-day probability")

    p.add_argument("--spike-chance", type=float)

    p.add_argument("--spike-mult", type=float, default=2.5)

    p.add_argument("--drop-chance", type=float)

    p.add_argument("--drop-mult", type=float, default=0.4)

    p.add_argument("--outlier-chance", type=float)

    p.add_argument("--outlier-mult", type=float, default=4)

    p.add_argument("--autocorr", type=float, help="AR(1) noise 0..0.9")

    p.add_argument("--trend-break", type=float, help="chance of mid-series trend shift")

    p.add_argument("--sku-scale-min", type=float, default=None)

    p.add_argument("--sku-scale-max", type=float, default=None)

    p.add_argument("--sku", action="append", default=["SKU-001", "SKU-002", "SKU-003"])

    p.add_argument("-o", "--output", type=Path, default=Path("demand_history.json"))

    args = p.parse_args()



    cfg = PRESETS[args.preset].copy()

    if args.preset == "xgboost_wins" and args.days == 365:

        args.days = int(cfg.get("days_default", 900))



    def pick(name, arg_val, key):

        if arg_val is not None:

            return arg_val

        return cfg[key]



    end = date.today()

    start = end - timedelta(days=args.days - 1)

    sku_lo = args.sku_scale_min if args.sku_scale_min is not None else cfg["sku_lo"]

    sku_hi = args.sku_scale_max if args.sku_scale_max is not None else cfg["sku_hi"]



    records = []

    for sku in args.sku:

        scale = sku_lo + random.random() * (sku_hi - sku_lo)

        trend = pick("trend", args.trend, "trend") * scale

        if random.random() < 0.35:

            trend *= -1

        for row in gen_series(

            args.days,

            start,

            pick("mean", args.mean, "mean") * scale,

            trend,

            pick("noise", args.noise, "noise"),

            pick("weekend", args.weekend, "weekend"),

            pick("holiday", args.holiday, "holiday"),

            pick("monthly", args.monthly, "monthly"),

            XGBOOST_WINS_WEEKDAY if args.preset == "xgboost_wins" else WEEKDAY_DEFAULT,

            pick("zero", args.zero, "zero"),

            spike_chance=pick("spike", args.spike_chance, "spike"),

            spike_mult=args.spike_mult,

            drop_chance=pick("drop", args.drop_chance, "drop"),

            drop_mult=args.drop_mult,

            outlier_chance=pick("outlier", args.outlier_chance, "outlier"),

            outlier_mult=args.outlier_mult,

            autocorr=pick("autocorr", args.autocorr, "autocorr"),

            trend_break_chance=pick("trend_break", args.trend_break, "trend_break"),

            friday_boost=cfg.get("friday", 1.0),

            september_boost=cfg.get("september", 1.0),

        ):

            records.append({"sku": sku, **row})



    payload = {

        "comment": f"CLI history preset={args.preset}",

        "records": records,

    }

    if args.output.suffix.lower() == ".json":

        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    else:

        pd.DataFrame(records).to_csv(args.output, index=False)



    print(f"OK: preset={args.preset}, {len(records)} records -> {args.output}")





if __name__ == "__main__":

    main()


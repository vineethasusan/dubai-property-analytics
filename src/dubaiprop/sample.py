"""Sample data in the same schema as Dubai Land Department (DLD) open data.

Used when the real files are not present, so the project runs anywhere (tests, CI, a quick demo).
Prices are illustrative, roughly in line with 2024-2026 market levels per community, and are not
official figures. For real analysis, download the DLD files (see README) into data/raw/.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# community: (AED per sqm in Jan 2024 for flats, villa share, annual growth, gross rental yield, metro)
AREAS = {
    "Palm Jumeirah": (26000, 0.35, 0.16, 0.050, None),
    "Downtown Dubai": (24000, 0.0, 0.12, 0.055, "Burj Khalifa/Dubai Mall Metro Station"),
    "Dubai Marina": (17500, 0.0, 0.13, 0.064, "DMCC Metro Station"),
    "Jumeirah Beach Residence": (19000, 0.0, 0.12, 0.060, "Jumeirah Beach Residence 1"),
    "Business Bay": (16500, 0.0, 0.14, 0.066, "Business Bay Metro Station"),
    "DIFC": (22000, 0.0, 0.11, 0.058, "Financial Centre Metro Station"),
    "Dubai Hills Estate": (18000, 0.40, 0.17, 0.056, None),
    "Jumeirah Lake Towers": (12500, 0.0, 0.12, 0.072, "Jumeirah Lakes Towers"),
    "Jumeirah Village Circle": (10500, 0.10, 0.15, 0.078, None),
    "Arabian Ranches": (12000, 0.95, 0.15, 0.052, None),
    "Damac Hills": (11000, 0.45, 0.14, 0.060, None),
    "Town Square": (9500, 0.30, 0.13, 0.068, None),
    "International City": (6500, 0.0, 0.10, 0.090, None),
    "Dubai South": (8500, 0.25, 0.16, 0.070, None),
    "Dubai Silicon Oasis": (8500, 0.10, 0.11, 0.075, None),
    "Al Furjan": (11000, 0.35, 0.14, 0.066, "Al Furjan Metro Station"),
    "Dubai Sports City": (9000, 0.05, 0.12, 0.074, None),
    "Mirdif": (10000, 0.70, 0.09, 0.058, None),
    "Al Barsha": (11500, 0.30, 0.10, 0.065, "Mall of the Emirates Metro Station"),
    "Mohammed Bin Rashid City": (16000, 0.40, 0.15, 0.058, None),
}
ROOMS = ["Studio", "1 B/R", "2 B/R", "3 B/R", "4 B/R", "5 B/R"]
FLAT_SIZE = {"Studio": 38, "1 B/R": 70, "2 B/R": 115, "3 B/R": 165, "4 B/R": 230, "5 B/R": 300}
VILLA_SIZE = {"2 B/R": 170, "3 B/R": 240, "4 B/R": 320, "5 B/R": 450}


def transactions(n: int = 60_000, start="2024-01-01", end="2026-06-30", seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime(rng.integers(pd.Timestamp(start).value // 10**9, pd.Timestamp(end).value // 10**9, n),
                           unit="s").normalize()
    names = list(AREAS)
    weights = np.array([1.2, 1.3, 1.6, 0.6, 1.8, 0.5, 1.3, 1.2, 2.2, 0.6, 1.0, 0.9, 0.9, 1.1, 0.8, 0.9, 0.8, 0.4, 0.6, 1.0])
    area = rng.choice(names, n, p=weights / weights.sum())
    rows = []
    # building/project quality premium: same project, consistently pricier or cheaper (view, developer, age)
    proj_premium = {(a, k): rng.lognormal(0, 0.10) for a in names for k in range(1, 25)}
    for i in range(n):
        a = area[i]
        base, villa_share, growth, _, metro = AREAS[a]
        villa = rng.random() < villa_share
        rooms = rng.choice(list(VILLA_SIZE) if villa else ROOMS, p=[0.2, 0.4, 0.3, 0.1] if villa else
                           [0.18, 0.36, 0.28, 0.12, 0.04, 0.02])
        size = (VILLA_SIZE if villa else FLAT_SIZE)[rooms] * rng.lognormal(0, 0.15)
        off_plan = rng.random() < (0.55 if a in ("Dubai South", "Jumeirah Village Circle", "Business Bay",
                                                 "Mohammed Bin Rashid City", "Dubai Hills Estate") else 0.3)
        years = (dates[i] - pd.Timestamp(start)).days / 365.25
        g = growth * (0.7 if dates[i] >= pd.Timestamp("2026-01-01") else 1.0)     # market cooling in 2026
        ppsm = base * (1 + g) ** years
        ppsm *= (1.12 if villa else 1.0) * (0.93 if off_plan else 1.0)
        ppsm *= {"Studio": 1.08, "1 B/R": 1.03, "2 B/R": 1.0, "3 B/R": 0.98, "4 B/R": 1.0, "5 B/R": 1.04}[rooms]
        proj = int(rng.integers(1, 25))
        ppsm *= proj_premium[(a, proj)]
        ppsm *= rng.lognormal(0, 0.10)                                            # unit-level: floor, view, finish
        price = round(ppsm * size, -3)
        rows.append({
            "transaction_id": f"1-{rng.integers(100, 999)}-{dates[i].year}-{i + 1}",
            "procedure_name_en": "Sell - Pre registration" if off_plan else "Sell",
            "trans_group_en": "Sales",
            "instance_date": dates[i].strftime("%d-%m-%Y"),
            "property_type_en": "Villa" if villa else "Unit",
            "property_sub_type_en": "Villa" if villa else "Flat",
            "property_usage_en": "Residential",
            "reg_type_en": "Off-Plan Properties" if off_plan else "Existing Properties",
            "area_name_en": a,
            "project_name_en": f"{a} Project {proj}",
            "rooms_en": rooms,
            "has_parking": int(rng.random() < 0.9),
            "procedure_area": round(size, 2),
            "actual_worth": price,
            "meter_sale_price": round(price / size, 2),
            "nearest_metro_en": metro,
        })
    df = pd.DataFrame(rows).sort_values("instance_date", key=lambda s: pd.to_datetime(s, format="%d-%m-%Y"))
    # a few data-quality problems found in real registries
    bad = rng.choice(len(df), 40, replace=False)
    df.iloc[bad[:20], df.columns.get_loc("actual_worth")] = 1            # nominal transfers
    df.iloc[bad[20:], df.columns.get_loc("procedure_area")] = 0.01       # area missing
    return df.reset_index(drop=True)


def rent_contracts(n: int = 40_000, start="2024-01-01", end="2026-06-30", seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime(rng.integers(pd.Timestamp(start).value // 10**9, pd.Timestamp(end).value // 10**9, n),
                           unit="s").normalize()
    names = list(AREAS)
    area = rng.choice(names, n)
    rows = []
    for i in range(n):
        base, villa_share, growth, yld, _ = AREAS[area[i]]
        villa = rng.random() < villa_share
        rooms = rng.choice(list(VILLA_SIZE) if villa else ROOMS[:5])
        size = (VILLA_SIZE if villa else FLAT_SIZE)[rooms] * rng.lognormal(0, 0.15)
        years = (dates[i] - pd.Timestamp(start)).days / 365.25
        value = base * (1 + growth * 0.8) ** years * size * (1.12 if villa else 1)
        rent = round(value * yld * rng.lognormal(0, 0.12), -2)
        rows.append({"contract_id": f"R{i + 1:06d}", "contract_start_date": dates[i].strftime("%d-%m-%Y"),
                     "contract_reg_type_en": rng.choice(["New", "Renew"], p=[0.45, 0.55]),
                     "area_name_en": area[i], "ejari_property_type_en": "Villa" if villa else "Flat",
                     "ejari_property_sub_type_en": rooms, "actual_area": round(size, 1), "annual_amount": rent,
                     "property_usage_en": "Residential"})
    return pd.DataFrame(rows)

"""Load and clean Dubai Land Department transactions and rent contracts.

Real data (recommended): put DLD open-data CSVs in data/raw/
  * data/raw/transactions.csv    - from dubailand.gov.ae/en/open-data/real-estate-data  (Transactions)
                                   or Dubai Pulse dataset dld_transactions-open
  * data/raw/rent_contracts.csv  - same sources (Rents / dld_rent_contracts-open)

Column names differ slightly between the DLD website export and Dubai Pulse, so each field
has a list of accepted aliases. If none match, the error lists the columns found so the
alias table can be extended in one line.

Without real files, a sample in the same schema is generated (clearly labelled as sample).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import sample

RAW = Path("data/raw")

TXN_ALIASES = {
    "date": ["instance_date", "transaction date", "instance date", "date"],
    "area": ["area_name_en", "area", "area name", "area_en", "community"],
    "price": ["actual_worth", "amount", "trans value", "transaction value", "actual worth", "price"],
    "size_sqm": ["procedure_area", "property size (sq.m)", "procedure area", "size", "area (sqm)", "actual area"],
    "rooms": ["rooms_en", "rooms", "room(s)", "no. of rooms", "bedrooms"],
    "sub_type": ["property_sub_type_en", "property sub type", "property_sub_type", "sub type"],
    "reg_type": ["reg_type_en", "registration type", "reg type", "is offplan", "property status"],
    "usage": ["property_usage_en", "usage", "property usage"],
    "group": ["trans_group_en", "transaction type", "trans group", "transaction group"],
    "procedure": ["procedure_name_en", "transaction sub type", "procedure", "procedure name"],
    "project": ["project_name_en", "project", "project name"],
    "metro": ["nearest_metro_en", "nearest metro"],
    "parking": ["has_parking", "parking"],
}
RENT_ALIASES = {
    "date": ["contract_start_date", "start date", "contract start date", "registration date"],
    "area": ["area_name_en", "area", "area name", "community"],
    "annual_rent": ["annual_amount", "annual amount", "contract amount", "amount", "rent"],
    "size_sqm": ["actual_area", "property size (sq.m)", "size", "area (sqm)"],
    "rooms": ["ejari_property_sub_type_en", "property sub type", "rooms", "bedrooms"],
    "prop_type": ["ejari_property_type_en", "property type"],
    "usage": ["property_usage_en", "usage", "property usage"],
}


def _resolve(df: pd.DataFrame, aliases: dict, required: list[str], what: str) -> pd.DataFrame:
    lower = {c.lower().strip(): c for c in df.columns}
    out = pd.DataFrame(index=df.index)
    for field, names in aliases.items():
        src = next((lower[n] for n in names if n in lower), None)
        if src is not None:
            out[field] = df[src]
        elif field in required:
            raise ValueError(f"{what}: no column found for '{field}'. Columns in file: {list(df.columns)}. "
                             f"Add the right name to the alias list in load.py.")
    return out


def _dates(s: pd.Series) -> pd.Series:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y", "%Y-%m-%d %H:%M:%S"):
        d = pd.to_datetime(s, format=fmt, errors="coerce")
        if d.notna().mean() > 0.9:
            return d
    return pd.to_datetime(s, errors="coerce", dayfirst=True)


def rooms_to_num(s: pd.Series) -> pd.Series:
    t = s.astype(str).str.lower()
    num = t.str.extract(r"(\d+)")[0].astype(float)
    num[t.str.contains("studio")] = 0
    return num


def clean_transactions(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = _resolve(raw, TXN_ALIASES, ["date", "area", "price", "size_sqm"], "transactions")
    n0 = len(df)
    df["date"] = _dates(df["date"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["size_sqm"] = pd.to_numeric(df["size_sqm"], errors="coerce")
    report = {"rows_in": n0}
    if "group" in df:
        df = df[df["group"].astype(str).str.contains("sale", case=False, na=False)]
    if "usage" in df:
        df = df[df["usage"].astype(str).str.contains("resid", case=False, na=False)]
    report["after_sales_residential_filter"] = len(df)
    df = df[(df["price"] >= 100_000) & (df["size_sqm"].between(15, 5000)) & df["date"].notna()]
    df["price_per_sqm"] = df["price"] / df["size_sqm"]
    # drop extreme price/sqm outliers per area (data entry errors, bulk deals, gifts)
    q = df.groupby("area")["price_per_sqm"].transform
    n_area = df.groupby("area")["price_per_sqm"].transform("size")
    lo, hi = q(lambda s: s.quantile(0.005)), q(lambda s: s.quantile(0.995))
    df = df[(n_area < 200) | ((df["price_per_sqm"] >= lo) & (df["price_per_sqm"] <= hi))]
    report["after_quality_filters"] = len(df)
    df["rooms_num"] = rooms_to_num(df["rooms"]) if "rooms" in df else np.nan
    df["is_villa"] = df["sub_type"].astype(str).str.contains("villa|townhouse", case=False).astype(int) \
        if "sub_type" in df else 0
    df["off_plan"] = df["reg_type"].astype(str).str.contains("off", case=False).astype(int) if "reg_type" in df else 0
    df["near_metro"] = df["metro"].notna().astype(int) if "metro" in df else 0
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df.sort_values("date").reset_index(drop=True), report


def clean_rents(raw: pd.DataFrame) -> pd.DataFrame:
    df = _resolve(raw, RENT_ALIASES, ["date", "area", "annual_rent"], "rent contracts")
    df["date"] = _dates(df["date"])
    df["annual_rent"] = pd.to_numeric(df["annual_rent"], errors="coerce")
    if "usage" in df:
        df = df[df["usage"].astype(str).str.contains("resid", case=False, na=False)]
    df = df[(df["annual_rent"].between(10_000, 5_000_000)) & df["date"].notna()]
    df["rooms_num"] = rooms_to_num(df["rooms"]) if "rooms" in df else np.nan
    df["is_villa"] = df["prop_type"].astype(str).str.contains("villa", case=False).astype(int) if "prop_type" in df else 0
    return df.reset_index(drop=True)


def load(raw_dir: Path = RAW) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    tx_path, rent_path = raw_dir / "transactions.csv", raw_dir / "rent_contracts.csv"
    if tx_path.exists():
        tx_raw, source = pd.read_csv(tx_path, low_memory=False), "DLD open data"
    else:
        tx_raw, source = sample.transactions(), "sample (DLD schema)"
    rent_raw = pd.read_csv(rent_path, low_memory=False) if rent_path.exists() else sample.rent_contracts()
    tx, rep = clean_transactions(tx_raw)
    rents = clean_rents(rent_raw)
    rep.update({"source": source, "rent_source": "DLD open data" if rent_path.exists() else "sample (DLD schema)",
                "rent_contracts": len(rents), "date_range": [str(tx["date"].min().date()), str(tx["date"].max().date())]})
    return tx, rents, rep

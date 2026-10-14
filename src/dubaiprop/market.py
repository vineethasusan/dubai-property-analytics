"""Market analytics: price index by community, momentum, rental yields and an investor matrix."""
from __future__ import annotations

import numpy as np
import pandas as pd


def monthly_index(tx: pd.DataFrame) -> pd.DataFrame:
    return (tx.groupby(["area", "month"]).agg(median_ppsm=("price_per_sqm", "median"), transactions=("price", "size"),
                                              off_plan_share=("off_plan", "mean"), total_value=("price", "sum"))
            .reset_index())


def community_summary(tx: pd.DataFrame, rents: pd.DataFrame) -> pd.DataFrame:
    end = tx["date"].max()
    last12 = tx[tx["date"] > end - pd.DateOffset(months=12)]
    prev12 = tx[(tx["date"] <= end - pd.DateOffset(months=12)) & (tx["date"] > end - pd.DateOffset(months=24))]
    s = last12.groupby("area").agg(transactions_12m=("price", "size"), median_price=("price", "median"),
                                   median_ppsm=("price_per_sqm", "median"), off_plan_share=("off_plan", "mean"),
                                   villa_share=("is_villa", "mean"))
    s["yoy_price_change"] = s["median_ppsm"] / prev12.groupby("area")["price_per_sqm"].median() - 1

    # Gross rental yield, like-for-like: median rent / median price for the same community, type and bedrooms
    r12 = rents[rents["date"] > end - pd.DateOffset(months=12)]
    key = ["area", "is_villa", "rooms_num"]
    price_seg = last12.groupby(key)["price"].median()
    rent_seg = r12.groupby(key)["annual_rent"].median()
    n_seg = r12.groupby(key).size()
    seg = pd.DataFrame({"price": price_seg, "rent": rent_seg, "n": n_seg}).dropna()
    seg = seg[seg["n"] >= 20]
    seg["yield"] = seg["rent"] / seg["price"]
    s["gross_rental_yield"] = seg.groupby("area").apply(lambda g: np.average(g["yield"], weights=g["n"]))

    gy, gg = s["gross_rental_yield"].median(), s["yoy_price_change"].median()
    s["investor_profile"] = np.select(
        [(s["gross_rental_yield"] >= gy) & (s["yoy_price_change"] >= gg),
         (s["gross_rental_yield"] >= gy), (s["yoy_price_change"] >= gg)],
        ["High yield + strong growth", "Income play (high yield)", "Growth play (capital gains)"],
        default="Mature / prime (lower yield and growth)")
    return s.sort_values("transactions_12m", ascending=False)


def market_overview(tx: pd.DataFrame) -> dict:
    end = tx["date"].max()
    last12 = tx[tx["date"] > end - pd.DateOffset(months=12)]
    prev12 = tx[(tx["date"] <= end - pd.DateOffset(months=12)) & (tx["date"] > end - pd.DateOffset(months=24))]
    return {"transactions_12m": int(len(last12)), "value_12m_aed_bn": round(last12["price"].sum() / 1e9, 1),
            "median_ppsm_12m": round(float(last12["price_per_sqm"].median())),
            "yoy_median_ppsm": round(float(last12["price_per_sqm"].median() / prev12["price_per_sqm"].median() - 1), 3),
            "off_plan_share_12m": round(float(last12["off_plan"].mean()), 3)}

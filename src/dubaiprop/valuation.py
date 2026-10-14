"""Automated valuation model (AVM): fair price range for a Dubai home.

Target is log(price per sqm). Besides the property's own attributes, the model gets a
"comparables" signal: the median price per sqm of similar homes (same community and type)
sold in the previous 3 months, computed only from earlier months (no look-ahead).
Validation is out-of-time: train on everything before the last 3 months, test on them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES = ["area_code", "is_villa", "off_plan", "rooms_num", "log_size", "near_metro", "months_since_start",
            "comp_ppsm_3m", "comp_count_3m", "area_ppsm_12m", "project_premium", "project_sales"]


class Valuer:
    def fit(self, tx: pd.DataFrame, as_of: pd.Timestamp | None = None):
        self.areas = sorted(tx["area"].unique())
        self.start = tx["month"].min()
        train = self._features(tx, tx)
        if as_of is not None:
            train = train[train["date"] <= as_of]
        self.history = tx if as_of is None else tx[tx["date"] <= as_of]
        y = np.log(train["price_per_sqm"])
        cat = [FEATURES.index("area_code")]
        kw = dict(max_iter=500, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=30, categorical_features=cat,
                  random_state=42)
        self.p50 = HistGradientBoostingRegressor(**kw).fit(train[FEATURES], y)
        self.p10 = HistGradientBoostingRegressor(loss="quantile", quantile=0.1, **kw).fit(train[FEATURES], y)
        self.p90 = HistGradientBoostingRegressor(loss="quantile", quantile=0.9, **kw).fit(train[FEATURES], y)
        return self

    def _features(self, rows: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
        f = rows.copy()
        f["_rid"] = np.arange(len(f))
        f["area_code"] = pd.Categorical(f["area"], categories=self.areas).codes
        f["log_size"] = np.log(f["size_sqm"])
        f["months_since_start"] = (f["month"].dt.year - self.start.year) * 12 + (f["month"].dt.month - self.start.month)
        # comparables: monthly medians by area x type, then a trailing 3-month window that ends the month before
        m = history.groupby(["area", "is_villa", "month"])["price_per_sqm"].agg(["median", "size"]).reset_index()
        comps = []
        for (a, v), g in m.groupby(["area", "is_villa"]):
            g = g.set_index("month").asfreq("MS")
            med = g["median"].rolling(3, min_periods=1).median().shift(1)
            cnt = g["size"].rolling(3, min_periods=1).sum().shift(1)
            comps.append(pd.DataFrame({"area": a, "is_villa": v, "month": g.index, "comp_ppsm_3m": med.values,
                                       "comp_count_3m": cnt.values}))
        comps = pd.concat(comps)
        am = history.groupby(["area", "month"])["price_per_sqm"].median().reset_index()
        a12 = []
        for a, g in am.groupby("area"):
            g = g.set_index("month").asfreq("MS")
            a12.append(pd.DataFrame({"area": a, "month": g.index,
                                     "area_ppsm_12m": g["price_per_sqm"].rolling(12, min_periods=1).median().shift(1).values}))
        f = f.merge(comps, on=["area", "is_villa", "month"], how="left").merge(pd.concat(a12), on=["area", "month"], how="left")
        # Project (building) premium: how this project's past sales priced vs its community, using only
        # sales from earlier months. In Dubai, the building is one of the strongest price drivers.
        if "project" in history and "project" in f:
            h = history.dropna(subset=["project"]).copy()
            h["rel"] = np.log(h["price_per_sqm"]) - np.log(h.groupby(["area", "month"])["price_per_sqm"].transform("median"))
            pm = h.groupby(["project", "month"])["rel"].agg(["sum", "size"]).reset_index().sort_values("month")
            pm["cum_sum"] = pm.groupby("project")["sum"].cumsum() - pm["sum"]       # strictly earlier months
            pm["cum_n"] = pm.groupby("project")["size"].cumsum() - pm["size"]
            pm = pm[["project", "month", "cum_sum", "cum_n"]]
            pm["project"] = pm["project"].astype(str)
            f["project"] = f["project"].fillna("__unknown__").astype(str)
            f = pd.merge_asof(f.sort_values("month"), pm.sort_values("month"), on="month", by="project",
                              direction="backward", allow_exact_matches=True)
            shrink = f["cum_n"] / (f["cum_n"] + 10)                                 # few sales -> trust less
            f["project_premium"] = (f["cum_sum"] / f["cum_n"].replace(0, np.nan)).fillna(0) * shrink.fillna(0)
            f["project_sales"] = f["cum_n"].fillna(0)
            f = f.drop(columns=["cum_sum", "cum_n"])
        else:
            f["project_premium"], f["project_sales"] = 0.0, 0.0
        f = f.sort_values("_rid").reset_index(drop=True)
        # for future dates beyond the history, carry the latest comparables forward
        # (historical rows keep NaN when there was nothing earlier: no look-ahead)
        future = f["month"] > history["month"].max()
        for c in ("comp_ppsm_3m", "comp_count_3m", "area_ppsm_12m"):
            if f.loc[future, c].isna().any():
                latest = (comps if c != "area_ppsm_12m" else pd.concat(a12)).dropna(subset=[c])
                key = ["area", "is_villa"] if c != "area_ppsm_12m" else ["area"]
                last = latest.sort_values("month").groupby(key)[c].last()
                fill = f[key].apply(tuple, axis=1).map(last.to_dict()) if len(key) > 1 else f["area"].map(last)
                f.loc[future, c] = f.loc[future, c].fillna(fill[future])
        return f

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        f = self._features(rows, self.history)            # same row order as `rows`
        out = pd.DataFrame(index=rows.index)
        for q, m in (("p10", self.p10), ("p50", self.p50), ("p90", self.p90)):
            out[f"value_{q}"] = np.exp(m.predict(f[FEATURES])) * rows["size_sqm"].values
        out["value_p10"] = np.minimum(out["value_p10"], out["value_p50"])
        out["value_p90"] = np.maximum(out["value_p90"], out["value_p50"])
        return out

    def value_home(self, area: str, size_sqm: float, rooms: float, villa: bool, off_plan: bool,
                   near_metro: bool = False, asking_price: float | None = None, project: str | None = None) -> dict:
        month = self.history["month"].max() + pd.offsets.MonthBegin(1)
        row = pd.DataFrame([{"area": area, "size_sqm": size_sqm, "rooms_num": rooms, "is_villa": int(villa),
                             "off_plan": int(off_plan), "near_metro": int(near_metro), "month": month,
                             "project": project}])
        v = self.predict(row).iloc[0].to_dict()
        res = {k: round(val, -3) for k, val in v.items()}
        res["price_per_sqm_p50"] = round(v["value_p50"] / size_sqm)
        if asking_price:
            if asking_price < v["value_p10"]:
                res["verdict"] = "Below fair range: good deal, or check for issues"
            elif asking_price > v["value_p90"]:
                res["verdict"] = "Above fair range: overpriced, negotiate"
            else:
                res["verdict"] = "Within fair range"
            res["asking_vs_fair_pct"] = round(100 * (asking_price / v["value_p50"] - 1), 1)
        return res


def backtest(tx: pd.DataFrame, test_months: int = 3) -> tuple[dict, pd.DataFrame]:
    cutoff = tx["month"].max() - pd.DateOffset(months=test_months - 1)
    train_end = cutoff - pd.Timedelta(days=1)
    v = Valuer().fit(tx, as_of=train_end)
    test = tx[tx["month"] >= cutoff].copy()
    pred = v.predict(test)
    test = test.join(pred)
    ape = np.abs(test["value_p50"] / test["price"] - 1)
    # baseline: median price/sqm of the same community and type over the 3 months before the cutoff
    hist = tx[(tx["date"] <= train_end) & (tx["month"] >= cutoff - pd.DateOffset(months=3))]
    med = hist.groupby(["area", "is_villa"])["price_per_sqm"].median()
    bl = test.set_index(["area", "is_villa"]).index.map(med.to_dict()).to_numpy(float) * test["size_sqm"].to_numpy()
    ape_bl = np.abs(bl / test["price"].to_numpy() - 1)
    within = (test["price"] >= test["value_p10"]) & (test["price"] <= test["value_p90"])
    metrics = {"test_period": [str(cutoff.date()), str(tx["date"].max().date())], "test_transactions": int(len(test)),
               "median_ape": round(float(np.median(ape)), 4), "mape": round(float(ape.mean()), 4),
               "within_10pct": round(float((ape <= 0.10).mean()), 3), "within_20pct": round(float((ape <= 0.20).mean()), 3),
               "baseline_median_ape": round(float(np.nanmedian(ape_bl)), 4),
               "baseline_within_10pct": round(float(np.nanmean(ape_bl <= 0.10)), 3),
               "p10_p90_coverage": round(float(within.mean()), 3)}
    return metrics, test

"""Dubai property dashboard: market trends, valuation tool and investor view.

    streamlit run dashboard.py      (run `make pipeline` first)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

st.set_page_config(page_title="Dubai Property Analytics", page_icon="🏙️", layout="wide")
OUT = Path("outputs")
if not (OUT / "valuer.joblib").exists():
    st.error("Run `make pipeline` first.")
    st.stop()


@st.cache_resource
def load_valuer():
    return joblib.load(OUT / "valuer.joblib")


@st.cache_data
def load_tables():
    return (pd.read_csv(OUT / "price_index.csv", parse_dates=["month"]),
            pd.read_csv(OUT / "community_summary.csv", index_col=0), json.loads((OUT / "metrics.json").read_text()))


valuer = load_valuer()
idx, comm, m = load_tables()
mk, vb = m["market"], m["valuation_backtest"]

st.title("🏙️ Dubai Property Analytics")
st.caption(f"Residential sales · source: {m['data']['source']} · {m['data']['date_range'][0]} to {m['data']['date_range'][1]}")
k = st.columns(5)
k[0].metric("Sales (12 months)", f"{mk['transactions_12m']:,}")
k[1].metric("Value (12 months)", f"AED {mk['value_12m_aed_bn']}bn")
k[2].metric("Median price", f"AED {mk['median_ppsm_12m'] / 10.764:,.0f}/sqft", f"{mk['yoy_median_ppsm']:+.1%} YoY")
k[3].metric("Off-plan share", f"{mk['off_plan_share_12m']:.0%}")
k[4].metric("Valuation accuracy", f"{vb['within_10pct']:.0%} within 10%", f"median error {vb['median_ape']:.1%}",
            delta_color="off")

t1, t2, t3 = st.tabs(["📈 Market", "🏠 Value a home", "💼 Investor view"])
with t1:
    areas = st.multiselect("Communities", sorted(idx["area"].unique()),
                           default=["Dubai Marina", "Downtown Dubai", "Jumeirah Village Circle", "Palm Jumeirah"])
    piv = idx[idx["area"].isin(areas)].pivot(index="month", columns="area", values="median_ppsm") / 10.764
    st.markdown("**Median price per sqft (AED)**")
    st.line_chart(piv, height=320)
    vol = idx[idx["area"].isin(areas)].pivot(index="month", columns="area", values="transactions")
    st.markdown("**Monthly sales**")
    st.bar_chart(vol, height=220)

with t2:
    c1, c2, c3 = st.columns(3)
    area = c1.selectbox("Community", sorted(comm.index))
    villa = c1.radio("Type", ["Apartment", "Villa / townhouse"], horizontal=True) != "Apartment"
    rooms = c2.selectbox("Bedrooms", [0, 1, 2, 3, 4, 5], index=1, format_func=lambda r: "Studio" if r == 0 else f"{r} BR")
    size_sqft = c2.number_input("Size (sqft)", 300, 15000, 800, step=50)
    off_plan = c3.checkbox("Off-plan")
    metro = c3.checkbox("Near metro")
    asking = c3.number_input("Asking price (AED, optional)", 0, 100_000_000, 0, step=50_000)
    r = valuer.value_home(area, size_sqft / 10.764, rooms, villa, off_plan, metro, asking or None)
    v = st.columns(4)
    v[0].metric("Fair value", f"AED {r['value_p50']:,.0f}")
    v[1].metric("Fair range (P10–P90)", f"{r['value_p10'] / 1e6:,.2f}M – {r['value_p90'] / 1e6:,.2f}M")
    v[2].metric("Price per sqft", f"AED {r['price_per_sqm_p50'] / 10.764:,.0f}")
    if asking:
        v[3].metric("Asking vs fair value", f"{r['asking_vs_fair_pct']:+.1f}%", r["verdict"], delta_color="off")
    st.caption("Estimate from recent comparable sales and property attributes. Not a formal valuation.")

with t3:
    st.markdown("Gross rental yield vs. year-on-year price growth by community (last 12 months).")
    c = comm.dropna(subset=["gross_rental_yield"]).reset_index().rename(columns={"index": "area"})
    c["yield_pct"] = c["gross_rental_yield"] * 100
    c["growth_pct"] = c["yoy_price_change"] * 100
    st.scatter_chart(c, x="growth_pct", y="yield_pct", color="investor_profile", size="transactions_12m", height=380)
    st.dataframe(c[["area", "transactions_12m", "median_ppsm", "growth_pct", "yield_pct", "investor_profile"]]
                 .sort_values("yield_pct", ascending=False).style.format(
                     {"median_ppsm": "{:,.0f}", "growth_pct": "{:+.1f}%", "yield_pct": "{:.1f}%"}),
                 hide_index=True, use_container_width=True)

"""End-to-end run: load/clean -> valuation backtest -> production valuer -> market & yield analytics.

    python -m dubaiprop.pipeline
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib

from . import market
from .load import load
from .valuation import Valuer, backtest

OUT = Path("outputs")


def main():
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    tx, rents, rep = load()
    print(f"Data source: {rep['source']} | {rep['after_quality_filters']:,} clean sales | {rep['date_range']}")
    metrics, test = backtest(tx)
    valuer = Valuer().fit(tx)
    joblib.dump(valuer, OUT / "valuer.joblib")
    idx = market.monthly_index(tx)
    idx.to_csv(OUT / "price_index.csv", index=False)
    comm = market.community_summary(tx, rents)
    comm.to_csv(OUT / "community_summary.csv")
    over = market.market_overview(tx)
    example = valuer.value_home("Dubai Marina", 75, 1, villa=False, off_plan=False, near_metro=True, asking_price=1_950_000)
    result = {"data": rep, "valuation_backtest": metrics, "market": over, "example_valuation": example,
              "runtime_s": round(time.time() - t0)}
    (OUT / "metrics.json").write_text(json.dumps(result, indent=2, default=str))

    L = [f"# Dubai residential market & valuation: results", "", f"_Data source: {rep['source']}, "
         f"{rep['date_range'][0]} to {rep['date_range'][1]}, {rep['after_quality_filters']:,} clean sales "
         f"(from {rep['rows_in']:,} records)._", "", "## Market (last 12 months)", "",
         f"- {over['transactions_12m']:,} sales worth AED {over['value_12m_aed_bn']}bn",
         f"- Median price AED {over['median_ppsm_12m']:,}/sqm (AED {over['median_ppsm_12m'] / 10.764:,.0f}/sqft), "
         f"**{over['yoy_median_ppsm']:+.1%}** year on year", f"- Off-plan share {over['off_plan_share_12m']:.0%}", "",
         "## Valuation model (out-of-time test)", "",
         f"Test period {metrics['test_period'][0]} to {metrics['test_period'][1]}, {metrics['test_transactions']:,} sales.", "",
         "| Metric | Model | Community-median baseline |", "|---|---|---|",
         f"| Median error | **{metrics['median_ape']:.1%}** | {metrics['baseline_median_ape']:.1%} |",
         f"| Within 10% of sale price | **{metrics['within_10pct']:.0%}** | {metrics['baseline_within_10pct']:.0%} |",
         f"| Within 20% | {metrics['within_20pct']:.0%} | |",
         f"| Sale price inside P10–P90 range | {metrics['p10_p90_coverage']:.0%} | |", "",
         "## Communities", "", "| Community | Sales (12m) | AED/sqm | YoY | Gross yield | Investor profile |",
         "|---|---|---|---|---|---|"]
    L += [f"| {a} | {int(r.transactions_12m):,} | {r.median_ppsm:,.0f} | {r.yoy_price_change:+.1%} | "
          f"{r.gross_rental_yield:.1%} | {r.investor_profile} |" for a, r in comm.iterrows()]
    L += ["", "## Example valuation", "", "1-bedroom, 75 sqm, Dubai Marina, ready, near metro, asking AED 1,950,000:", "",
          f"- Fair value AED {example['value_p50']:,.0f} (range {example['value_p10']:,.0f} – {example['value_p90']:,.0f})",
          f"- Verdict: **{example['verdict']}** ({example['asking_vs_fair_pct']:+}% vs fair value)"]
    (OUT / "report.md").write_text("\n".join(L) + "\n")
    print(f"Done in {result['runtime_s']}s -> outputs/report.md")
    print(json.dumps(metrics, indent=1))
    print(example)


if __name__ == "__main__":
    main()

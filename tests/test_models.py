from dubaiprop import market
from dubaiprop.valuation import Valuer, backtest


def test_valuation_beats_community_median(tx_rents):
    tx, _ = tx_rents
    m, _ = backtest(tx)
    assert m["median_ape"] < m["baseline_median_ape"]
    assert 0.6 <= m["p10_p90_coverage"] <= 0.95


def test_bigger_home_is_worth_more(tx_rents):
    tx, _ = tx_rents
    v = Valuer().fit(tx)
    small = v.value_home("Dubai Marina", 70, 1, False, False)
    big = v.value_home("Dubai Marina", 140, 2, False, False)
    assert big["value_p50"] > small["value_p50"]


def test_prime_area_costs_more_per_sqm(tx_rents):
    tx, _ = tx_rents
    v = Valuer().fit(tx)
    assert v.value_home("Palm Jumeirah", 100, 2, False, False)["price_per_sqm_p50"] > \
        v.value_home("International City", 100, 2, False, False)["price_per_sqm_p50"]


def test_no_lookahead_in_comparables(tx_rents):
    tx, _ = tx_rents
    v = Valuer().fit(tx)
    f = v._features(tx, tx)
    first_month = f[f["month"] == f["month"].min()]
    assert first_month["comp_ppsm_3m"].isna().all()     # nothing earlier to compare with


def test_yields_are_plausible(tx_rents):
    tx, rents = tx_rents
    s = market.community_summary(tx, rents)
    y = s["gross_rental_yield"].dropna()
    assert ((y > 0.02) & (y < 0.15)).all()

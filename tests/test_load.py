import pandas as pd
import pytest

from dubaiprop.load import clean_transactions, rooms_to_num


def test_accepts_dld_website_style_headers():
    raw = pd.DataFrame({"Transaction Date": ["05-03-2026", "06-03-2026"], "Area": ["Dubai Marina", "Dubai Marina"],
                        "Amount": [1_500_000, 2_000_000], "Property Size (sq.m)": [80, 100],
                        "Rooms": ["1 B/R", "2 B/R"], "Transaction Type": ["Sales", "Sales"]})
    df, rep = clean_transactions(raw)
    assert len(df) == 2 and df["price_per_sqm"].tolist() == [18750, 20000]


def test_missing_required_column_gives_helpful_error():
    with pytest.raises(ValueError, match="Columns in file"):
        clean_transactions(pd.DataFrame({"foo": [1]}))


def test_quality_filters_drop_nominal_and_missing_size(tx_rents):
    tx, _ = tx_rents
    assert tx["price"].min() >= 100_000 and tx["size_sqm"].min() >= 15


def test_rooms_parsing():
    assert rooms_to_num(pd.Series(["Studio", "1 B/R", "3 B/R", "PENTHOUSE"])).fillna(-1).tolist() == [0, 1, 3, -1]

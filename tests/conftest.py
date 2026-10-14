import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(scope="session")
def tx_rents():
    from dubaiprop import sample
    from dubaiprop.load import clean_rents, clean_transactions

    tx, _ = clean_transactions(sample.transactions(n=15000, seed=3))
    return tx, clean_rents(sample.rent_contracts(n=12000, seed=4))

import pytest

from billing import tax_for


def test_tax_for_basic():
    assert tax_for(100, 0.08) == 8.0


def test_tax_for_negative_rate():
    with pytest.raises(ValueError):
        tax_for(100, -0.1)

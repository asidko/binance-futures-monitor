"""Price parsing accepts Binance's copied thousands-separator format (1,379.91)."""
import main
import pytest


def test_plain_decimal():
    assert main._parse_price("407.96") == 407.96


def test_integer():
    assert main._parse_price("65000") == 65000.0


def test_thousands_separator():
    assert main._parse_price("1,379.91") == 1379.91


def test_multiple_separators():
    assert main._parse_price("1,234,567.89") == 1234567.89


def test_thousands_without_decimal():
    assert main._parse_price("1,000,000") == 1000000.0


def test_garbage_rejected():
    with pytest.raises(ValueError):
        main._parse_price("abc")

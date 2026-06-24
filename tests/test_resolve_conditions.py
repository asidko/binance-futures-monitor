"""Compound condition tokens expand to concrete REGISTRY names at add-time."""
import conditions
import main
import pytest


def test_type_family_auto_picks_above_when_price_below_level():
    assert conditions.resolve_conditions(["closed"], 100.0, 110.0) == ["closed-above"]


def test_type_family_auto_picks_below_when_price_above_level():
    assert conditions.resolve_conditions(["closed"], 120.0, 110.0) == ["closed-below"]


def test_direction_family_takes_both_types():
    assert conditions.resolve_conditions(["above"], None, 110.0) == ["closed-above", "crosses-above"]


def test_full_name_passes_through():
    assert conditions.resolve_conditions(["closed-above"], None, 110.0) == ["closed-above"]


def test_default_both_types_auto_direction():
    assert conditions.resolve_conditions(["crosses", "closed"], 100.0, 110.0) == ["closed-above", "crosses-above"]


def test_overlapping_tokens_dedup():
    assert conditions.resolve_conditions(["above", "closed-above"], None, 110.0) == ["closed-above", "crosses-above"]


def test_type_family_without_price_errors():
    with pytest.raises(ValueError):
        conditions.resolve_conditions(["closed"], None, 110.0)


def test_unknown_token_errors():
    with pytest.raises(ValueError):
        conditions.resolve_conditions(["bogus"], 100.0, 110.0)


def test_is_condition_token():
    assert conditions.is_condition_token("closed")
    assert conditions.is_condition_token("above")
    assert conditions.is_condition_token("closed-above")
    assert conditions.is_condition_token("closed-green")
    assert conditions.is_condition_token("closed-opposite")
    assert not conditions.is_condition_token("bogus")


def test_closed_opposite_after_green_candle_arms_red():
    green = {"open": 10.0, "close": 12.0}
    assert conditions.resolve_conditions(["closed-opposite"], None, 0.0, candle=green) == ["closed-red"]


def test_closed_opposite_after_red_candle_arms_green():
    red = {"open": 12.0, "close": 10.0}
    assert conditions.resolve_conditions(["closed-opposite"], None, 0.0, candle=red) == ["closed-green"]


def test_closed_opposite_without_candle_errors():
    with pytest.raises(ValueError):
        conditions.resolve_conditions(["closed-opposite"], None, 0.0)


def test_color_full_name_passes_through():
    assert conditions.resolve_conditions(["closed-green"], None, 0.0) == ["closed-green"]


def test_default_conditions_reads_env(monkeypatch):
    monkeypatch.setenv("DEFAULT_CONDITION", "closed, crosses")
    assert main._default_conditions() == ["closed", "crosses"]


def test_default_conditions_falls_back_to_both_types(monkeypatch):
    monkeypatch.delenv("DEFAULT_CONDITION", raising=False)
    assert main._default_conditions() == list(conditions.CONDITION_TYPES)

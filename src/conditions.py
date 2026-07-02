"""conditions.py - named price/kline level conditions with built-in dedup.

Library module (imported by main.py), not a CLI. Each condition is
check(ctx, level, state) -> bool with dedup owned inside; registered by name in
REGISTRY for monitor's --condition. Add one = one function + one REGISTRY row.

  from conditions import REGISTRY
  cond = REGISTRY["crosses-above"]

ctx keys:
  price         - last price (always present)
  closed_kline  - last closed kline dict (present when any kline condition runs)
"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Condition:
    name: str
    kind: str  # "price" | "kline"
    check: Callable[[dict, float, dict], bool]


def _crosses_above(ctx: dict, level: float, state: dict) -> bool:
    above = ctx["price"] > level
    prev = state.get("above")
    state["above"] = above
    return prev is not None and not prev and above


def _crosses_below(ctx: dict, level: float, state: dict) -> bool:
    below = ctx["price"] < level
    prev = state.get("below")
    state["below"] = below
    return prev is not None and not prev and below


def _closed_above(ctx: dict, level: float, state: dict) -> bool:
    return _on_new_close(ctx, state, lambda k: k["close"] > level)


def _closed_below(ctx: dict, level: float, state: dict) -> bool:
    return _on_new_close(ctx, state, lambda k: k["close"] < level)


def _closed_green(ctx: dict, level: float, state: dict) -> bool:
    return _on_new_close(ctx, state, lambda k: k["close"] > k["open"])


def _closed_red(ctx: dict, level: float, state: dict) -> bool:
    return _on_new_close(ctx, state, lambda k: k["close"] < k["open"])


def _on_new_close(ctx: dict, state: dict, predicate: Callable[[dict], bool]) -> bool:
    kline = ctx["closed_kline"]
    prev_open_time = state.get("open_time")
    if prev_open_time is not None and kline["open_time"] <= prev_open_time:
        return False
    first = prev_open_time is None
    state["open_time"] = kline["open_time"]
    return not first and predicate(kline)


def _is_green(kline: dict) -> bool:
    return kline["close"] > kline["open"]


# A concrete condition name is "<type>-<qualifier>" (direction above/below, or
# color red/green). A compound token is a half on its own, a full name, or the
# "closed-opposite" auto-pick; all expand to concrete names at add-time.
CONDITION_TYPES = ("crosses", "closed")
CONDITION_DIRECTIONS = ("above", "below")
CONDITION_OPPOSITE = "closed-opposite"  # -> closed-red/green, opposite of the last closed candle

REGISTRY = {
    "crosses-above": Condition("crosses-above", "price", _crosses_above),
    "crosses-below": Condition("crosses-below", "price", _crosses_below),
    "closed-above": Condition("closed-above", "kline", _closed_above),
    "closed-below": Condition("closed-below", "kline", _closed_below),
    "closed-green": Condition("closed-green", "kline", _closed_green),
    "closed-red": Condition("closed-red", "kline", _closed_red),
}


def is_condition_token(token: str) -> bool:
    return (token in REGISTRY or token in CONDITION_TYPES
            or token in CONDITION_DIRECTIONS or token == CONDITION_OPPOSITE)


def valid_tokens() -> list[str]:
    return list(REGISTRY) + list(CONDITION_TYPES) + list(CONDITION_DIRECTIONS) + [CONDITION_OPPOSITE]


def resolve_conditions(tokens: list[str], price: float | None, level: float,
                       candle: dict | None = None) -> list[str]:
    """Expand compound tokens to sorted concrete REGISTRY names. A bare type
    ('closed') auto-picks its direction from price vs level; a bare direction
    ('above') takes both types; 'closed-opposite' takes the color opposite the
    last closed candle; a full name ('closed-above') passes through."""
    names: set[str] = set()
    for token in tokens:
        names.update(_expand(token, price, level, candle))
    return sorted(names)


def _expand(token: str, price: float | None, level: float, candle: dict | None) -> list[str]:
    if token in REGISTRY:
        return [token]
    if token in CONDITION_DIRECTIONS:
        return [f"{t}-{token}" for t in CONDITION_TYPES]
    if token in CONDITION_TYPES:
        if price is None:
            raise ValueError(f"condition '{token}' needs the current price to pick a direction")
        return [f"{token}-{'above' if price < level else 'below'}"]
    if token == CONDITION_OPPOSITE:
        if candle is None:
            raise ValueError(f"condition '{token}' needs the last closed candle to pick a color")
        return [f"closed-{'red' if _is_green(candle) else 'green'}"]
    raise ValueError(f"unknown condition: {token}")

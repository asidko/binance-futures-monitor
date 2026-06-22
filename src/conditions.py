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
    above = ctx["price"] > level
    prev = state.get("above")
    state["above"] = above
    return prev is not None and prev and not above


def _closed_above(ctx: dict, level: float, state: dict) -> bool:
    return _on_new_close(ctx, state, lambda close: close > level)


def _closed_below(ctx: dict, level: float, state: dict) -> bool:
    return _on_new_close(ctx, state, lambda close: close < level)


def _on_new_close(ctx: dict, state: dict, predicate: Callable[[float], bool]) -> bool:
    kline = ctx["closed_kline"]
    prev_open_time = state.get("open_time")
    if kline["open_time"] == prev_open_time:
        return False
    first = prev_open_time is None
    state["open_time"] = kline["open_time"]
    return not first and predicate(kline["close"])


# A concrete condition name is "<type>-<direction>". A compound token is either
# half on its own (or a full name); it expands to concrete names at add-time.
CONDITION_TYPES = ("crosses", "closed")
CONDITION_DIRECTIONS = ("above", "below")

REGISTRY = {
    "crosses-above": Condition("crosses-above", "price", _crosses_above),
    "crosses-below": Condition("crosses-below", "price", _crosses_below),
    "closed-above": Condition("closed-above", "kline", _closed_above),
    "closed-below": Condition("closed-below", "kline", _closed_below),
}


def is_condition_token(token: str) -> bool:
    return token in REGISTRY or token in CONDITION_TYPES or token in CONDITION_DIRECTIONS


def valid_tokens() -> list[str]:
    return list(REGISTRY) + list(CONDITION_TYPES) + list(CONDITION_DIRECTIONS)


def resolve_conditions(tokens: list[str], price: float | None, level: float) -> list[str]:
    """Expand compound tokens to sorted concrete REGISTRY names. A bare type
    ('closed') auto-picks its direction from price vs level; a bare direction
    ('above') takes both types; a full name ('closed-above') passes through."""
    names: set[str] = set()
    for token in tokens:
        names.update(_expand(token, price, level))
    return sorted(names)


def _expand(token: str, price: float | None, level: float) -> list[str]:
    if token in REGISTRY:
        return [token]
    if token in CONDITION_DIRECTIONS:
        return [f"{t}-{token}" for t in CONDITION_TYPES]
    if token in CONDITION_TYPES:
        if price is None:
            raise ValueError(f"condition '{token}' needs the current price to pick a direction")
        return [f"{token}-{'above' if price < level else 'below'}"]
    raise ValueError(f"unknown condition: {token}")

"""conditions.py - named price/kline level conditions with built-in dedup.

Library module (imported by monitor.py), not a CLI. Each condition is
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


CONDITION_AUTO_ABOVE_SUFFIX = "-above"
CONDITION_AUTO_BELOW_SUFFIX = "-below"

REGISTRY = {
    "crosses-above": Condition("crosses-above", "price", _crosses_above),
    "crosses-below": Condition("crosses-below", "price", _crosses_below),
    "closed-above": Condition("closed-above", "kline", _closed_above),
    "closed-below": Condition("closed-below", "kline", _closed_below),
}


def auto_conditions(price: float, level: float) -> list[Condition]:
    """Price below level -> all *above conditions; at/above -> all *below."""
    suffix = CONDITION_AUTO_ABOVE_SUFFIX if price < level else CONDITION_AUTO_BELOW_SUFFIX
    return [cond for name, cond in REGISTRY.items() if name.endswith(suffix)]

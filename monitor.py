#!/usr/bin/env python3
"""monitor.py - watch a futures symbol+level and alert on chosen conditions (deduped).

Usage: ./monitor.py --symbol <sym> --level <price> [--condition <name> ... | --condition-auto]

Options:
  --symbol <sym>       Futures symbol, e.g. DOGEUSDT.
  --level <price>      Price level to watch.
  --condition <name>   Condition to fire on; repeatable. One of: crosses-above, crosses-below, closed-above, closed-below.
  --condition-auto     Auto-pick by launch price vs level: below -> *above, at/above -> *below (default when no --condition).
  --timeframe <tf>     Kline timeframe for closed-* conditions (default: 15m).
  --provider <name>    Notification provider (default: telegram).
  --interval <sec>     Poll interval in seconds (default: 10).

Examples:
  ./monitor.py --symbol DOGEUSDT --level 0.08285
  ./monitor.py --symbol BTCUSDT --level 65000 --condition closed-above --condition closed-below --timeframe 1h
"""
import argparse
import logging
import sys
import time

import binance_client
import conditions
import config
from notifier import notify

log = logging.getLogger("monitor")


def build_message(symbol: str, cond: conditions.Condition, level: float, ctx: dict, timeframe: str) -> str:
    if cond.kind == "price":
        detail = f"price={ctx['price']}"
    else:
        detail = f"{timeframe} close={ctx['closed_kline']['close']}"
    return f"[{symbol}] {cond.name} {level} ({detail})"


def poll_once(args: argparse.Namespace, selected: list, state: dict, needs_kline: bool) -> None:
    ctx = {"price": binance_client.get_last_price(args.symbol)}
    if needs_kline:
        ctx["closed_kline"] = binance_client.get_last_closed_kline(args.symbol, args.timeframe)
    for cond in selected:
        if cond.check(ctx, args.level, state[cond.name]):
            message = build_message(args.symbol, cond, args.level, ctx, args.timeframe)
            log.info("FIRED %s", message)
            try:
                notify(message, args.provider)
            except Exception:
                log.exception("notify failed for %s", message)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        epilog=__doc__[__doc__.index("Examples:"):].rstrip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", metavar="<sym>", required=True, help="Futures symbol, e.g. DOGEUSDT.")
    parser.add_argument("--level", metavar="<price>", type=float, required=True, help="Price level to watch.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--condition", metavar="<name>", action="append", dest="conditions",
                       choices=list(conditions.REGISTRY),
                       help="Condition to fire on; repeatable. One of: " + ", ".join(conditions.REGISTRY) + ".")
    group.add_argument("--condition-auto", action="store_true",
                       help="Auto-pick by launch price vs level (default when no --condition).")
    parser.add_argument("--timeframe", metavar="<tf>", default="15m",
                        help="Kline timeframe for closed-* conditions (default: 15m).")
    parser.add_argument("--provider", metavar="<name>", default="telegram",
                        help="Notification provider (default: telegram).")
    parser.add_argument("--interval", metavar="<sec>", type=float, default=10.0,
                        help="Poll interval in seconds (default: 10).")
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config.load_env()

    if args.conditions:
        selected = [conditions.REGISTRY[name] for name in args.conditions]
    else:
        price_now = binance_client.get_last_price(args.symbol)
        selected = conditions.auto_conditions(price_now, args.level)
        rel = "below" if price_now < args.level else "at/above"
        log.info("auto: launch price %s %s level %s", price_now, rel, args.level)

    if not selected:
        log.error("no conditions selected")
        return 1

    needs_kline = any(cond.kind == "kline" for cond in selected)
    state = {cond.name: {} for cond in selected}
    cond_names = [cond.name for cond in selected]

    log.info("watching %s level=%s tf=%s conditions=%s interval=%ss provider=%s",
             args.symbol, args.level, args.timeframe, cond_names, args.interval, args.provider)

    while True:
        try:
            poll_once(args, selected, state, needs_kline)
        except Exception:
            log.exception("poll error")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())

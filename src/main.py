#!/usr/bin/env python3
"""main.py - watch Binance futures levels via a background daemon.

Usage: ./main.py <command> [options]

Commands:
  add      Add a one-shot watch (auto-removed after it fires once) and ensure the daemon is running.
  list     Show all watches.
  remove   Remove a watch by id, or all watches for a symbol.
  status   Show daemon state, watch count, last cycle.
  start    Ensure the daemon is running.
  stop     Stop the daemon.
  logs     Show the daemon log.

Examples:
  ./main.py add --symbol DOGEUSDT --level 0.08285
  ./main.py add --symbol BTCUSDT --level 65000 --timeframe 1h --condition closed-above --condition closed-below
  ./main.py list
  ./main.py remove --id 3
  ./main.py remove --symbol DOGEUSDT
  ./main.py status
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

import binance_client
import conditions
import config
import daemon as daemon_mod
import paths
import proclock
import store

_MIN_INTERVAL = 2.0
_WEDGED_CYCLES = 3


def _precheck_provider(provider: str) -> None:
    if provider == "telegram" and not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print("error: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env (copy .env.example)", file=sys.stderr)
        sys.exit(1)


def _ensure_daemon(interval: float) -> bool:
    if proclock.running_pid(paths.PIDFILE) is not None:
        return False
    paths.ensure_data_dir()
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "_daemon", "--interval", str(interval)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        start_new_session=True, close_fds=True, cwd=str(paths.ROOT),
    )
    return True


def cmd_add(args) -> int:
    config.load_env()
    _precheck_provider(args.provider)
    symbol = args.symbol.upper()
    if not binance_client.symbol_exists(symbol):
        print(f"error: unknown trading symbol {symbol}", file=sys.stderr)
        return 1
    interval = max(args.interval, _MIN_INTERVAL)
    if _seconds(args.timeframe) and interval > _seconds(args.timeframe):
        print(f"warning: interval {interval}s > timeframe {args.timeframe}; intermediate closed-* candles may be missed",
              file=sys.stderr)
    conn = store.connect()
    store.init_db(conn)
    watch_id, created = store.add_watch(conn, symbol, args.level, args.timeframe, args.conditions, args.provider)
    spawned = _ensure_daemon(interval)
    shown = ",".join(args.conditions) if args.conditions else "auto"
    print(f"{'added' if created else 'exists'} #{watch_id} {symbol} @ {args.level} [{shown}] {args.timeframe} ({args.provider})")
    print(f"daemon {'spawned' if spawned else 'already running'}")
    return 0


def cmd_list(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    watches = store.list_watches(conn)
    if args.json:
        print(json.dumps([w.__dict__ for w in watches], indent=2))
        return 0
    if not watches:
        print("no watches")
        return 0
    print(f"{'ID':>3}  {'SYMBOL':<12} {'LEVEL':>12}  {'TF':<4} {'CONDITIONS':<28} PROVIDER")
    for w in watches:
        conds = "auto" if w.conditions == "auto" else ",".join(json.loads(w.conditions))
        print(f"{w.id:>3}  {w.symbol:<12} {w.level:>12g}  {w.timeframe:<4} {conds:<28} {w.provider}")
    return 0


def cmd_remove(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    if args.id is not None:
        removed = store.remove_by_id(conn, args.id)
        print(f"removed {removed} watch(es) by id {args.id}")
    else:
        removed = store.remove_by_symbol(conn, args.symbol.upper())
        print(f"removed {removed} watch(es) for {args.symbol.upper()}")
    return 0


def cmd_status(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    pid = proclock.running_pid(paths.PIDFILE)
    meta = store.get_meta(conn)
    count = store.count_watches(conn)
    last = meta.get("last_cycle")
    age = int(time.time()) - last if last else None
    threshold = _WEDGED_CYCLES * max(args.interval, _MIN_INTERVAL)

    if count == 0 and pid is None:
        state, code = "IDLE (no watches)", 0
    elif pid is None:
        state, code = "DOWN", 3
    elif age is not None and age > threshold:
        state, code = "WEDGED", 3
    else:
        state, code = "UP", 0

    print(f"state:      {state}")
    print(f"pid:        {pid if pid else '-'}")
    print(f"watches:    {count}")
    print(f"last_cycle: {f'{age}s ago' if age is not None else 'never'}")
    print(f"log:        {paths.LOG}")
    if state == "DOWN":
        print("note: watches exist but daemon is down - run `main.py start`", file=sys.stderr)
    return code


def cmd_start(args) -> int:
    spawned = _ensure_daemon(max(args.interval, _MIN_INTERVAL))
    print("daemon spawned" if spawned else "already running")
    return 0


def cmd_stop(args) -> int:
    pid = proclock.running_pid(paths.PIDFILE)
    if pid is None:
        print("not running")
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if proclock.running_pid(paths.PIDFILE) is None:
            print(f"stopped (pid {pid})")
            return 0
        time.sleep(0.25)
    os.kill(pid, signal.SIGKILL)
    print(f"force-killed (pid {pid})")
    return 0


def cmd_logs(args) -> int:
    if not paths.LOG.exists():
        print("no log yet")
        return 0
    cmd = ["tail", "-f", str(paths.LOG)] if args.follow else ["tail", "-n", str(args.lines), str(paths.LOG)]
    return subprocess.run(cmd).returncode


def cmd_daemon(args) -> int:
    return daemon_mod.run_daemon(max(args.interval, _MIN_INTERVAL))


_TIMEFRAME_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def _seconds(timeframe: str) -> int:
    try:
        return int(timeframe[:-1]) * _TIMEFRAME_SECONDS[timeframe[-1]]
    except (ValueError, KeyError, IndexError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        epilog=__doc__[__doc__.index("Examples:"):].rstrip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="add a watch and ensure the daemon runs")
    p_add.add_argument("--symbol", metavar="<sym>", required=True)
    p_add.add_argument("--level", metavar="<price>", type=float, required=True)
    p_add.add_argument("--timeframe", metavar="<tf>", default="15m")
    p_add.add_argument("--condition", metavar="<name>", action="append", dest="conditions",
                       choices=list(conditions.REGISTRY),
                       help="repeatable; omit for auto (picks *above/*below by price vs level)")
    p_add.add_argument("--provider", metavar="<name>", default="telegram")
    p_add.add_argument("--interval", metavar="<sec>", type=float, default=10.0,
                       help="daemon poll cadence; applied when the daemon (re)starts")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="list watches")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="remove by id or symbol")
    group = p_remove.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=int, metavar="<id>")
    group.add_argument("--symbol", metavar="<sym>")
    p_remove.set_defaults(func=cmd_remove)

    p_status = sub.add_parser("status", help="daemon state")
    p_status.add_argument("--interval", type=float, default=10.0, help="expected cadence (for WEDGED check)")
    p_status.set_defaults(func=cmd_status)

    p_start = sub.add_parser("start", help="ensure the daemon is running")
    p_start.add_argument("--interval", metavar="<sec>", type=float, default=10.0)
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="stop the daemon")
    p_stop.set_defaults(func=cmd_stop)

    p_logs = sub.add_parser("logs", help="show the daemon log")
    p_logs.add_argument("--follow", "-f", action="store_true")
    p_logs.add_argument("--lines", "-n", type=int, default=40)
    p_logs.set_defaults(func=cmd_logs)

    p_daemon = sub.add_parser("_daemon")  # internal: the poll loop
    p_daemon.add_argument("--interval", type=float, default=10.0)
    p_daemon.set_defaults(func=cmd_daemon)

    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

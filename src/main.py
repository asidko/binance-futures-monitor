#!/usr/bin/env python3
"""main.py - watch Binance futures levels via a background daemon.

Usage: ./main.py <command> [options]

Commands:
  add      Add a one-shot watch (auto-removed after it fires once) and ensure the daemon is running.
  list     Show all watches.
  monitor  Stream alerts to this terminal until Ctrl-C.
  remove   Remove a watch by id, all watches for a symbol, or all watches.
  status   Show daemon state, watch count, last cycle.
  start    Ensure the daemon is running.
  stop     Stop the daemon.
  logs     Show the daemon log.

Examples:
  ./main.py add DOGEUSDT 0.08285                 (shorthand: symbol then levels)
  ./main.py add AVGOUSDT 407.96 406.74           (multiple levels, one watch each)
  ./main.py add BTCUSDT 65000 --provider file --file alerts.log
  ./main.py add --symbol BTCUSDT --level 65000 --timeframe 1h --condition closed-above --condition closed-below
  ./main.py monitor                              (watch alerts live, any provider)
  ./main.py list
  ./main.py remove --id 3
  ./main.py remove --all
  ./main.py status
"""
# Build flags for `nuitka` (a portable single-file binary). Applied whenever
# nuitka compiles this module, so source and CI builds stay identical.
# nuitka-project: --onefile
# nuitka-project: --output-dir={MAIN_DIRECTORY}/../dist
# nuitka-project: --output-filename=bfm
# nuitka-project: --include-package-data=certifi
# nuitka-project: --assume-yes-for-downloads
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
import notifier
import paths
import proclock
import store
import version

_MIN_INTERVAL = 2.0
_WEDGED_CYCLES = 3
_MONITOR_POLL = 0.5


def _provider_label(provider: str, arg: str | None) -> str:
    return f"{provider}:{arg}" if arg else provider


def _resolve_provider(args) -> tuple[str, str | None] | None:
    """Resolve the alert provider: explicit --provider, else DEFAULT_PROVIDER,
    else telegram when configured, else stdout. Telegram falls back to stdout
    unless explicitly requested. A provider's arg (path/url) and validation come
    from its notifier.REGISTRY entry, read from the same-named CLI flag dest."""
    explicit = args.provider is not None
    provider = (args.provider or os.environ.get("DEFAULT_PROVIDER") or "").strip().lower()
    if not provider:
        provider = "telegram" if notifier.telegram_configured() else "stdout"
    spec = notifier.REGISTRY.get(provider)
    if spec is None:
        print(f"error: unknown provider '{provider}' (have: {', '.join(notifier.PROVIDERS)})", file=sys.stderr)
        return None
    if provider == "telegram" and not notifier.telegram_configured():
        if explicit:
            print("error: --provider telegram but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set", file=sys.stderr)
            return None
        provider, spec = "stdout", notifier.REGISTRY["stdout"]
    if spec.arg_flag is None:
        return provider, None
    raw = getattr(args, provider)
    if not raw:
        print(f"error: --provider {provider} requires {spec.arg_flag}", file=sys.stderr)
        return None
    try:
        return provider, spec.validate(raw)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _daemon_argv(interval: float) -> list[str]:
    """Frozen: re-exec the real binary; source: python + this script."""
    head = [str(paths.EXECUTABLE)] if paths.FROZEN else [sys.executable, os.path.abspath(__file__)]
    return head + ["_daemon", "--interval", str(interval)]


def _ensure_daemon(interval: float) -> bool:
    if proclock.running_pid(paths.PIDFILE) is not None:
        return False
    paths.ensure_data_dir()
    subprocess.Popen(
        _daemon_argv(interval),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        start_new_session=True, close_fds=True, cwd=str(paths.DATA_DIR),
    )
    return True


def _resolve_target(args) -> tuple[str, list[float]] | None:
    """Merge flagged (--symbol/--level) and shorthand positional forms.
    Positional: the non-numeric token is the symbol, the rest are levels."""
    symbol = args.symbol
    levels = list(args.levels or [])
    for tok in args.rest:
        try:
            levels.append(float(tok))
        except ValueError:
            if symbol is not None:
                print(f"error: multiple symbols given ({symbol}, {tok})", file=sys.stderr)
                return None
            symbol = tok
    if not symbol or not levels:
        print("error: need a symbol and at least one level (e.g. `add AVGOUSDT 407.96 406.74`)", file=sys.stderr)
        return None
    return symbol.upper(), levels


def cmd_add(args) -> int:
    config.load()
    resolved = _resolve_provider(args)
    if resolved is None:
        return 1
    provider, provider_arg = resolved
    target = _resolve_target(args)
    if target is None:
        return 2
    symbol, levels = target
    if not binance_client.symbol_exists(symbol):
        print(f"error: unknown trading symbol {symbol}", file=sys.stderr)
        return 1
    interval = max(args.interval, _MIN_INTERVAL)
    if _seconds(args.timeframe) and interval > _seconds(args.timeframe):
        print(f"warning: interval {interval}s > timeframe {args.timeframe}; intermediate closed-* candles may be missed",
              file=sys.stderr)
    price = None if args.conditions else binance_client.get_last_price(symbol)
    conn = store.connect()
    store.init_db(conn)
    for level in levels:
        cond_names = args.conditions or [c.name for c in conditions.auto_conditions(price, level)]
        watch_id, created, stored_arg = store.add_watch(conn, symbol, level, args.timeframe, cond_names, provider, provider_arg)
        shown = ",".join(sorted(cond_names))
        print(f"{'added' if created else 'exists'} #{watch_id} {symbol} @ {level} [{shown}] {args.timeframe} ({_provider_label(provider, stored_arg)})")
        if not created and stored_arg != provider_arg:
            print(f"note: #{watch_id} already targets {_provider_label(provider, stored_arg)}; remove it first to retarget", file=sys.stderr)
    if provider == "stdout":
        print("alerts go to stdout - watch them live with `bfm monitor`")
    spawned = _ensure_daemon(interval)
    print(f"monitoring {'started' if spawned else 'already running'}")
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
        conds = ",".join(json.loads(w.conditions))
        provider = _provider_label(w.provider, w.provider_arg)
        print(f"{w.id:>3}  {w.symbol:<12} {w.level:>12g}  {w.timeframe:<4} {conds:<28} {provider}")
    return 0


def cmd_remove(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    if args.all:
        removed = store.remove_all(conn)
        print(f"removed {removed} watch(es)")
    elif args.id is not None:
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


def cmd_monitor(args) -> int:
    conn = store.connect()
    store.init_db(conn)
    if proclock.running_pid(paths.PIDFILE) is None:
        print("note: daemon is not running - start it with `bfm start` or add a watch", file=sys.stderr)
    after = store.latest_alert_id(conn)
    print("watching for alerts (Ctrl-C to stop)...", file=sys.stderr)
    try:
        while True:
            for alert_id, ts, message in store.alerts_after(conn, after):
                stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                print(f"{stamp}  {message}", flush=True)
                after = alert_id
            time.sleep(_MONITOR_POLL)
    except KeyboardInterrupt:
        return 0


def cmd_start(args) -> int:
    spawned = _ensure_daemon(max(args.interval, _MIN_INTERVAL))
    print("monitoring started" if spawned else "monitoring already running")
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
    config.load()
    return daemon_mod.run_daemon(max(args.interval, _MIN_INTERVAL))


_TIMEFRAME_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def _seconds(timeframe: str) -> int:
    try:
        return int(timeframe[:-1]) * _TIMEFRAME_SECONDS[timeframe[-1]]
    except (ValueError, KeyError, IndexError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bfm",
        description=version.banner(),
        epilog=__doc__[__doc__.index("Examples:"):].rstrip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=version.banner())
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="add a watch and ensure the daemon runs")
    p_add.add_argument("rest", nargs="*", metavar="<symbol> <level>...",
                       help="shorthand: `add AVGOUSDT 407.96 406.74` (symbol then levels)")
    p_add.add_argument("--symbol", metavar="<sym>")
    p_add.add_argument("--level", metavar="<price>", type=float, action="append", dest="levels",
                       help="repeatable; each level becomes its own watch")
    p_add.add_argument("--timeframe", metavar="<tf>", default="15m")
    p_add.add_argument("--condition", metavar="<name>", action="append", dest="conditions",
                       choices=list(conditions.REGISTRY),
                       help="repeatable; omit to auto-pick *above/*below by current price vs level")
    p_add.add_argument("--provider", metavar="<name>", choices=notifier.PROVIDERS, default=None,
                       help=f"{' | '.join(notifier.PROVIDERS)}; omit for DEFAULT_PROVIDER or telegram, falling back to stdout")
    p_add.add_argument("--file", metavar="<path>", help="output file for the file provider")
    p_add.add_argument("--callback-url", metavar="<url>", dest="callback",
                       help="GET this URL (with ?message=...) for the callback provider")
    p_add.add_argument("--interval", metavar="<sec>", type=float, default=10.0,
                       help="daemon poll cadence; applied when the daemon (re)starts")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="list watches")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_monitor = sub.add_parser("monitor", help="stream alerts to this terminal until Ctrl-C")
    p_monitor.set_defaults(func=cmd_monitor)

    p_remove = sub.add_parser("remove", help="remove by id, symbol, or all")
    group = p_remove.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=int, metavar="<id>")
    group.add_argument("--symbol", metavar="<sym>")
    group.add_argument("--all", action="store_true", help="remove every watch")
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

"""daemon.py - the polling loop: read store, dedup-fetch, evaluate, alert.

Library module, not a CLI. Launched via `main.py _daemon`. Holds the flock
for its whole life, persists dedup state per watch (survives restart), fetches
all prices in one call, isolates per-symbol failures, and auto-exits when the
watchlist stays empty. Watches are one-shot: the first condition to fire
deletes the watch (state cascades), so it never re-alerts.
"""
import json
import logging
import os
import signal
import sys
import time
from logging.handlers import RotatingFileHandler

import binance_client
import conditions
import paths
import proclock
import store
from notifier import notify

log = logging.getLogger("daemon")

_EXIT_AFTER_EMPTY = 3
_stop = False


def _handle_stop(signum, frame) -> None:
    global _stop
    _stop = True


def _setup_logging() -> None:
    handler = RotatingFileHandler(paths.LOG, maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    sys.excepthook = lambda et, e, tb: log.error("uncaught", exc_info=(et, e, tb))


def _message(watch: store.Watch, cond, ctx: dict) -> str:
    if cond.kind == "price":
        detail = f"price={ctx['price']}"
    else:
        detail = f"{watch.timeframe} close={ctx['closed_kline']['close']}"
    return f"[#{watch.id} {watch.symbol}] {cond.name} {watch.level} ({detail})"


def _eval_watch(conn, watch: store.Watch, prices: dict, klines: dict) -> None:
    if watch.symbol not in prices:
        log.warning("watch %s: no price for %s", watch.id, watch.symbol)
        return
    ctx = {"price": prices[watch.symbol]}
    kline = klines.get((watch.symbol, watch.timeframe))
    if kline is not None:
        ctx["closed_kline"] = kline

    state = store.load_state(conn, watch.id)
    before = json.dumps(state, sort_keys=True)
    names = json.loads(watch.conditions)

    for name in names:
        cond = conditions.REGISTRY.get(name)
        if cond is None:
            continue
        if cond.kind == "kline" and "closed_kline" not in ctx:
            continue
        cstate = state.setdefault(name, {})
        if cond.check(ctx, watch.level, cstate):
            message = _message(watch, cond, ctx)
            log.info("FIRED %s", message)
            try:
                notify(message, watch.provider, watch.provider_arg)
            except Exception:
                log.exception("notify failed, keeping watch %s to retry", watch.id)
                return  # don't persist consumed state -> re-evaluates next cycle
            store.record_alert(conn, message)  # broadcast to `bfm monitor`, any provider
            store.remove_by_id(conn, watch.id)  # one-shot: alert delivered, auto-delete (state cascades)
            log.info("auto-removed watch %s after alert", watch.id)
            return

    if json.dumps(state, sort_keys=True) != before:
        store.save_state(conn, watch.id, state)


def run_once(conn) -> None:
    watches = store.list_watches(conn)
    prices = binance_client.get_all_prices()
    klines: dict = {}
    for symbol, timeframe in {(w.symbol, w.timeframe) for w in watches}:
        try:
            klines[(symbol, timeframe)] = binance_client.get_last_closed_kline(symbol, timeframe)
        except binance_client.RateLimited:
            raise
        except Exception:
            log.exception("kline fetch failed %s %s", symbol, timeframe)
    for watch in watches:
        try:
            _eval_watch(conn, watch, prices, klines)
        except Exception:
            log.exception("watch %s eval failed", watch.id)


def run_daemon(interval: float) -> int:
    lock = proclock.DaemonLock(paths.PIDFILE)
    if not lock.acquire():
        return 0  # another daemon won the spawn race
    _setup_logging()
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    conn = store.connect()
    store.init_db(conn)
    store.set_started(conn)
    log.info("daemon up pid=%s interval=%ss", os.getpid(), interval)
    empty = 0
    try:
        while not _stop:
            try:
                if store.count_watches(conn) == 0:
                    empty += 1
                    if empty >= _EXIT_AFTER_EMPTY:
                        log.info("watchlist empty -> exiting")
                        break
                else:
                    empty = 0
                    run_once(conn)
                store.set_heartbeat(conn)
            except binance_client.RateLimited as exc:
                log.warning("rate limited; backing off %ss", exc.retry_after)
                _sleep(exc.retry_after)
                continue
            except Exception:
                log.exception("cycle error")
            _sleep(interval)
    finally:
        log.info("daemon stopped")
        lock.release()
    return 0


def _sleep(seconds: float) -> None:
    end = time.monotonic() + seconds
    while not _stop:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.5, remaining))

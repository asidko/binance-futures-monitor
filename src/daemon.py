"""daemon.py - the polling loop: read store, dedup-fetch, evaluate, alert.

Library module, not a CLI. Launched via `main.py _daemon`. Holds the flock
for its whole life, persists dedup state per watch (survives restart), fetches
all prices in one call, isolates per-symbol failures, and auto-exits when the
watchlist stays empty. Each condition is one-shot: firing alerts once and drops
that condition; the watch is deleted when its last condition fires.
"""
import copy
import json
import logging
import os
import signal
import sqlite3
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
_ACQUIRE_TRIES = 3  # a `status`/`monitor` probe flock can transiently collide with ours
_KLINE_LOOKBACK = 10  # closed candles per fetch; covers gaps from backoff/suspend
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


def _needs_klines(watch: store.Watch) -> bool:
    return any(cond.kind == "kline"
               for name in json.loads(watch.conditions)
               if (cond := conditions.REGISTRY.get(name)) is not None)


def _eval_watch(conn, watch: store.Watch, prices: dict, klines: dict) -> None:
    if watch.symbol not in prices:
        log.warning("watch %s: no price for %s", watch.id, watch.symbol)
        return
    price = prices[watch.symbol]
    candles = klines.get((watch.symbol, watch.timeframe), [])

    state = store.load_state(conn, watch.id)
    before = json.dumps(state, sort_keys=True)
    names = json.loads(watch.conditions)

    fired = []
    for name in names:
        cond = conditions.REGISTRY.get(name)
        if cond is None:
            continue
        cstate = state.setdefault(name, {})
        if cond.kind == "price":
            ctxs = [{"price": price}]
        elif cstate.get("open_time") is None:
            # first observation: baseline on the NEWEST candle only - older
            # fetched candles closed before this watch existed
            ctxs = [{"price": price, "closed_kline": c} for c in candles[-1:]]
        else:
            # every closed candle since the last seen one (ascending); the
            # condition's own open_time monotonic guard skips stale ones
            ctxs = [{"price": price, "closed_kline": c} for c in candles]
        for ctx in ctxs:
            prev = copy.deepcopy(cstate)
            if not cond.check(ctx, watch.level, cstate):
                continue
            message = _message(watch, cond, ctx)
            log.info("FIRED %s", message)
            try:
                notify(message, watch.provider, watch.provider_arg)
            except Exception:
                state[name] = prev  # un-consume: leave it active, re-fire next cycle
                log.exception("notify failed, keeping condition %s on watch %s", name, watch.id)
                break
            fired.append(name)
            try:
                store.record_alert(conn, message)  # best-effort broadcast to `bfm monitor`
            except Exception:
                log.exception("record_alert failed for watch %s (alert already delivered)", watch.id)
            break  # one-shot: this condition is retired, skip its remaining candles

    if fired:
        _retire_fired(conn, watch, names, fired, state)
    elif json.dumps(state, sort_keys=True) != before:
        try:
            store.save_state(conn, watch.id, state)
        except sqlite3.IntegrityError:
            log.info("watch %s removed underneath us; state discarded", watch.id)


def _retire_fired(conn, watch: store.Watch, names: list, fired: list, state: dict) -> None:
    remaining = [n for n in names if n not in fired]
    for name in fired:
        state.pop(name, None)
    outcome = store.retire_fired(conn, watch, remaining, state)
    if outcome == "deleted":
        log.info("auto-removed watch %s after last condition fired", watch.id)
    elif outcome == "updated":
        log.info("watch %s: %s fired, %s still active", watch.id, fired, remaining)
    elif outcome == "redundant":
        log.info("watch %s redundant after %s fired (matched existing); removed", watch.id, fired)
    else:
        log.info("watch %s changed underneath us; retire skipped", watch.id)


def run_once(conn) -> float | None:
    """One evaluation cycle. Returns a backoff in seconds when a kline fetch
    was rate limited (evaluation still ran on the data already in hand)."""
    watches = store.list_watches(conn)
    prices = binance_client.get_all_prices()
    klines: dict = {}
    backoff = None
    for symbol, timeframe in {(w.symbol, w.timeframe) for w in watches if _needs_klines(w)}:
        if _stop or backoff is not None:  # one 429 means the IP budget is hit; stop digging
            break
        try:
            klines[(symbol, timeframe)] = binance_client.get_closed_klines(
                symbol, timeframe, limit=_KLINE_LOOKBACK)
        except binance_client.RateLimited as exc:
            backoff = exc.retry_after
        except Exception:
            log.exception("kline fetch failed %s %s", symbol, timeframe)
    for watch in watches:
        if _stop:
            break
        try:
            _eval_watch(conn, watch, prices, klines)
        except Exception:
            log.exception("watch %s eval failed", watch.id)
    return backoff


def run_daemon(interval: float) -> int:
    lock = proclock.DaemonLock(paths.PIDFILE)
    for attempt in range(_ACQUIRE_TRIES):
        if lock.acquire():
            break
        time.sleep(0.15)
    else:
        return 0  # another daemon won the spawn race
    _setup_logging()
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    conn = store.connect()
    store.init_db(conn)
    store.set_started(conn, interval)
    log.info("daemon up pid=%s interval=%ss", os.getpid(), interval)
    empty = 0
    try:
        while not _stop:
            try:
                if store.count_watches(conn) == 0:
                    empty += 1
                    if empty >= _EXIT_AFTER_EMPTY:
                        if _handoff_exit(lock, conn):
                            log.info("watchlist empty -> exiting")
                            break
                        empty = 0
                        continue
                else:
                    empty = 0
                    backoff = run_once(conn)
                    if backoff is not None:
                        log.warning("rate limited; backing off %ss", backoff)
                        _backoff(conn, backoff, interval)
                        continue
                store.set_heartbeat(conn)
            except binance_client.RateLimited as exc:  # the price snapshot itself was limited
                log.warning("rate limited; backing off %ss", exc.retry_after)
                _backoff(conn, exc.retry_after, interval)
                continue
            except Exception:
                log.exception("cycle error")
            _sleep(interval)
    finally:
        log.info("daemon stopped")
        lock.release()
    return 0


def _handoff_exit(lock, conn) -> bool:
    """Close the exit-vs-add race: release the lock BEFORE the final emptiness
    check, so a concurrent `add` either finds the lock free (spawns a fresh
    daemon) or its watch is visible here (we re-acquire and keep going)."""
    lock.release()
    if store.count_watches(conn) == 0:
        return True
    if not lock.acquire():
        return True  # a freshly spawned daemon took over
    return False


def _backoff(conn, seconds: float, interval: float) -> None:
    """Rate-limit sleep that keeps stamping the heartbeat so `status` reports
    a backing-off daemon as UP, not WEDGED."""
    end = time.monotonic() + seconds
    while not _stop:
        store.set_heartbeat(conn)
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        _sleep(min(interval, remaining))


def _sleep(seconds: float) -> None:
    end = time.monotonic() + seconds
    while not _stop:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.5, remaining))

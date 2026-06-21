"""Per-condition retire: firing one condition keeps its siblings armed; the
watch is deleted only when its last condition fires."""
import json

import daemon
import store


def _eval(conn, price, close, open_time):
    watch = store.list_watches(conn)[0]
    klines = {(watch.symbol, watch.timeframe): {"close": close, "open_time": open_time}}
    daemon._eval_watch(conn, watch, {watch.symbol: price}, klines)


def _conditions(conn):
    watches = store.list_watches(conn)
    return json.loads(watches[0].conditions) if watches else None


def test_firing_one_condition_keeps_the_sibling(conn, monkeypatch):
    sent = []
    monkeypatch.setattr(daemon, "notify", lambda msg, prov, arg=None: sent.append(msg))
    store.add_watch(conn, "DOGEUSDT", 0.10, "15m",
                    ["crosses-above", "closed-above"], "stdout", None)

    _eval(conn, 0.09, 0.09, 1000)              # baseline, no fire
    assert _conditions(conn) == ["closed-above", "crosses-above"]
    assert sent == []

    _eval(conn, 0.11, 0.09, 1000)              # crosses-above fires, same candle
    assert _conditions(conn) == ["closed-above"]
    assert len(sent) == 1

    _eval(conn, 0.11, 0.12, 2000)              # new candle closes above -> last fires
    assert _conditions(conn) is None
    assert len(sent) == 2


def test_notify_failure_leaves_condition_armed(conn, monkeypatch):
    down = {"on": True}

    def notify(msg, prov, arg=None):
        if down["on"]:
            raise RuntimeError("send down")

    monkeypatch.setattr(daemon, "notify", notify)
    store.add_watch(conn, "DOGEUSDT", 0.10, "15m", ["crosses-above"], "stdout", None)

    _eval(conn, 0.09, 0.09, 1000)              # baseline
    _eval(conn, 0.11, 0.09, 1000)              # cross, but notify fails
    assert _conditions(conn) == ["crosses-above"]

    down["on"] = False
    _eval(conn, 0.11, 0.12, 2000)              # recovered -> fires and clears
    assert _conditions(conn) is None

"""closed-green / closed-red fire on a candle that closes that color; the first
observation only sets a baseline, and the same candle never re-fires."""
import conditions


def _check(name, kline, state):
    return conditions.REGISTRY[name].check({"price": 0.0, "closed_kline": kline}, 0.0, state)


def test_closed_green_fires_on_a_new_green_close():
    state = {}
    assert not _check("closed-green", {"open_time": 1, "open": 10, "close": 9}, state)   # baseline
    assert _check("closed-green", {"open_time": 2, "open": 9, "close": 11}, state)       # green close
    assert not _check("closed-green", {"open_time": 2, "open": 9, "close": 11}, state)   # same candle


def test_closed_red_fires_on_a_new_red_close():
    state = {}
    assert not _check("closed-red", {"open_time": 1, "open": 10, "close": 11}, state)    # baseline
    assert _check("closed-red", {"open_time": 2, "open": 11, "close": 9}, state)         # red close


def test_green_condition_ignores_a_red_close():
    state = {}
    _check("closed-green", {"open_time": 1, "open": 10, "close": 9}, state)              # baseline
    assert not _check("closed-green", {"open_time": 2, "open": 11, "close": 9}, state)   # red, no fire

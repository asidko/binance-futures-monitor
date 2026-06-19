"""binance_client.py - read-only Binance USD-M futures REST helpers.

Library module (imported by monitor.py and other tools), not a CLI.

  from binance_client import get_last_price, get_last_closed_kline
  price = get_last_price("DOGEUSDT")
  kline = get_last_closed_kline("DOGEUSDT", "15m")  # last CLOSED candle
"""
import requests

BASE = "https://fapi.binance.com"
_TIMEOUT = 10


def get_last_price(symbol: str) -> float:
    resp = requests.get(f"{BASE}/fapi/v1/ticker/price", params={"symbol": symbol}, timeout=_TIMEOUT)
    resp.raise_for_status()
    return float(resp.json()["price"])


def get_last_closed_kline(symbol: str, interval: str) -> dict:
    resp = requests.get(
        f"{BASE}/fapi/v1/klines",
        params={"symbol": symbol, "interval": interval, "limit": 2},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    # Last element is the still-forming candle; [-2] is the most recent closed one.
    k = data[-2] if len(data) >= 2 else data[-1]
    return {
        "open_time": k[0],
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "close_time": k[6],
    }

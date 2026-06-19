"""binance_client.py - read-only Binance USD-M futures REST helpers.

Library module, not a CLI.

  from binance_client import get_all_prices, get_last_closed_kline, symbol_exists
"""
import requests

BASE = "https://fapi.binance.com"
_TIMEOUT = 10


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


def _get(path: str, params: dict | None = None):
    resp = requests.get(f"{BASE}{path}", params=params, timeout=_TIMEOUT)
    if resp.status_code in (418, 429):
        raise RateLimited(float(resp.headers.get("Retry-After", 60)))
    resp.raise_for_status()
    return resp.json()


def get_all_prices() -> dict[str, float]:
    """All symbol last prices in ONE call (flat weight) - scales to any N."""
    return {row["symbol"]: float(row["price"]) for row in _get("/fapi/v1/ticker/price")}


def get_last_price(symbol: str) -> float:
    return float(_get("/fapi/v1/ticker/price", {"symbol": symbol})["price"])


def get_last_closed_kline(symbol: str, interval: str) -> dict:
    data = _get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 2})
    # Last element is the still-forming candle; [-2] is the most recent closed one.
    k = data[-2] if len(data) >= 2 else data[-1]
    return {"open_time": k[0], "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]), "close_time": k[6]}


def get_trading_symbols() -> set[str]:
    data = _get("/fapi/v1/exchangeInfo")
    return {s["symbol"] for s in data["symbols"] if s.get("status") == "TRADING"}


def symbol_exists(symbol: str) -> bool:
    return symbol in get_trading_symbols()

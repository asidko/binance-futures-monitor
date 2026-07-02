"""binance_client.py - read-only Binance USD-M futures REST helpers.

Library module, not a CLI.

  from binance_client import get_all_prices, get_closed_klines, symbol_exists
"""
import requests

BASE = "https://fapi.binance.com"
_TIMEOUT = 10
_session = requests.Session()

VALID_TIMEFRAMES = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h",
                    "6h", "8h", "12h", "1d", "3d", "1w", "1M")


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


def _get(path: str, params: dict | None = None):
    resp = _session.get(f"{BASE}{path}", params=params, timeout=_TIMEOUT)
    if resp.status_code in (418, 429):
        raise RateLimited(float(resp.headers.get("Retry-After", 60)))
    resp.raise_for_status()
    return resp.json()


def get_all_prices() -> dict[str, float]:
    """All symbol last prices in ONE call (flat weight) - scales to any N."""
    return {row["symbol"]: float(row["price"]) for row in _get("/fapi/v1/ticker/price")}


def get_last_price(symbol: str) -> float:
    return float(_get("/fapi/v1/ticker/price", {"symbol": symbol})["price"])


def _parse_kline(k: list) -> dict:
    return {"open_time": k[0], "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]), "close_time": k[6]}


def get_closed_klines(symbol: str, interval: str, limit: int = 10) -> list[dict]:
    """The most recent CLOSED candles, ascending. The API's last element is the
    still-forming candle and is dropped; a brand-new listing may have none."""
    data = _get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    return [_parse_kline(k) for k in data[:-1]]


def get_last_closed_kline(symbol: str, interval: str) -> dict | None:
    closed = get_closed_klines(symbol, interval, limit=2)
    return closed[-1] if closed else None


def get_trading_symbols() -> set[str]:
    data = _get("/fapi/v1/exchangeInfo")
    return {s["symbol"] for s in data["symbols"] if s.get("status") == "TRADING"}


def symbol_exists(symbol: str) -> bool:
    return symbol in get_trading_symbols()

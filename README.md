# binance-futures-monitor

Modular read-only scripts to spot situations on Binance USD-M futures.
CLI tools are self-contained (one job); shared logic lives in small libs.
Run any tool with no args to see its help.

## Setup

```
uv sync
cp .env.example .env   # fill TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
```

Run tools with `uv run ./<tool>.py ...` (or activate `.venv` and call `./<tool>.py`).

## Tools

notifier.py - sends messages (alerts) with given provider
Usage: ./notifier.py --message <text> [--provider <provider>]  # default: telegram
Example: ./notifier.py --message '[DOGE] Kline closed ABOVE the level'

monitor.py - watch a symbol+level, alert when conditions fire (deduped)
Usage: ./monitor.py --symbol <sym> --level <price> [--condition <name> ... | --condition-auto] [--timeframe 15m] [--provider telegram] [--interval 10]
Example: ./monitor.py --symbol DOGEUSDT --level 0.08285   # auto: below level -> *above, at/above -> *below

## Libs (imported, not run)

binance_client.py - read-only futures REST helpers (last price, last closed kline)
  from binance_client import get_last_price, get_last_closed_kline

conditions.py - named level conditions with built-in dedup; registry for monitor's --condition
  Conditions: crosses-above, crosses-below, closed-above, closed-below

## Notes

- Uses Last price (matches a line drawn on the chart), not Mark.
- Dedup state is in-memory: a restart re-arms each condition.
- REST polling, not websocket: a cross is only as fine as `--interval`; a fast wick through the level and back between polls is missed.

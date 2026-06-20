# binance-futures-monitor

Set a price level on any Binance USD-M futures symbol. When price hits it, `bfm`
sends an alert (e.g. Telegram) and drops the watch. The background daemon polls
all your watches at once.

## Install

Prebuilt single-file binary (Linux / macOS, x86_64 / arm64), no Python needed:

```
curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh
```

Installs `bfm` to `~/.local/bin` and creates `~/.bfm/.env`. Uninstall:

```
curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh -s -- --remove
```

Or grab a binary straight from the [latest release](https://github.com/asidko/binance-futures-monitor/releases/latest) and `chmod +x`.

## Configure

Put your Telegram bot token and chat id in `~/.bfm/.env`:

```
TELEGRAM_BOT_TOKEN=123456:abc...
TELEGRAM_CHAT_ID=987654321
```

## Use

```
bfm add DOGEUSDT 0.08285              # symbol then level(s)
bfm add AVGOUSDT 407.96 406.74        # multiple levels, one watch each
bfm list
bfm status
bfm remove --symbol DOGEUSDT
bfm logs --follow
bfm stop
```

- Omit conditions and `bfm` picks the direction from the current price: if price
  is below your level it alerts when price rises to it; if at or above, it alerts
  when price falls to it. `list` shows the exact conditions it chose.
- Pick conditions explicitly with flags:
  `bfm add --symbol BTCUSDT --level 65000 --timeframe 1h --condition closed-above`
- Conditions: `crosses-above`, `crosses-below`, `closed-above`, `closed-below`.
- `--interval` sets the daemon poll cadence; applied when the daemon (re)starts.

## Develop / build from source

Run from source with [uv](https://docs.astral.sh/uv/) (anchors `.env` and data
to the repo root instead of `~/.bfm`):

```
uv sync
cp .env.example .env   # don't forget to fix bot token here
uv run ./src/main.py add DOGEUSDT 0.08285
```

Build the portable binary (pinned to Python 3.13; flags live in
`# nuitka-project:` comments in `src/main.py`):

```
uv run python scripts/build.py     # -> dist/bfm-<os>-<arch>
```

Releases are built per-OS by `.github/workflows/release.yml` on a `v*` tag.

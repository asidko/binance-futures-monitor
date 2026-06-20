# binance-futures-monitor

Watch Binance USD-M futures for price/level situations and get a Telegram alert
when one fires. One small CLI (`bfm`) drives a background daemon that polls many
symbol+level watches and alerts on named conditions. Each watch is one-shot: it
fires once, then removes itself.

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

- Omit conditions and `bfm` auto-picks by current price: below the level it
  watches `*above`, at/above it watches `*below`. Resolved at add-time, so
  `list` always shows the real conditions.
- Pick conditions explicitly with flags:
  `bfm add --symbol BTCUSDT --level 65000 --timeframe 1h --condition closed-above`
- Conditions: `crosses-above`, `crosses-below`, `closed-above`, `closed-below`.
- `--interval` sets the daemon poll cadence; applied when the daemon (re)starts.

## How it works

`bfm` is both the CLI and (via an internal flag) the daemon. The watchlist lives
in SQLite under `~/.bfm/.monitor-data/` - the CLI writes it, the daemon reads it
each poll cycle. `add` spawns the daemon if it isn't running; the daemon
auto-exits when the watchlist empties. A watch fires once and then deletes
itself; the alert is the commit point, so a failed Telegram send keeps the watch
to retry rather than dropping the alert. Override the data dir with `BFM_DATA_DIR`.

## Notes / accepted limits

- Liveness is respawn-on-CLI-only (no systemd): if the daemon dies while idle it
  stays down until the next `add`/`start`. `status` reports UP/DOWN/WEDGED
  (exit 3 when down).
- Uses Last price (matches a line drawn on the chart), not Mark.
- A cycle reads the latest CLOSED candle; if `--interval` > timeframe,
  intermediate `closed-*` candles can be missed (`add` warns).
- REST polling, not websocket; cross detection is only as fine as `--interval`.

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

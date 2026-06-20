# binance-futures-monitor

Set a price level on any Binance USD-M futures symbol. When price hits it, `bfm`
sends an alert (e.g. Telegram) and drops the watch. The background daemon polls
all your watches at once.

## Install

Prebuilt single-file binary (Linux / macOS, x86_64 / arm64), no Python needed:

```
curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh
```

Installs `bfm` to `~/.local/bin`. Uninstall:

```
curl -fsSL https://raw.githubusercontent.com/asidko/binance-futures-monitor/main/install.sh | sh -s -- --remove
```

Or grab a binary straight from the [latest release](https://github.com/asidko/binance-futures-monitor/releases/latest) and `chmod +x`.

## Configure

`bfm` creates `~/.config/bfm/config.toml` on first run. For Telegram alerts, fill
it in:

```toml
default_provider = "telegram"   # telegram | stdout | file | callback

[telegram]
bot_token = "123456:abc..."
chat_id = "987654321"
```

Leave it empty and alerts default to stdout, which you watch live with `bfm monitor`.

## Use

```
bfm add DOGEUSDT 0.08285              # symbol then level(s)
bfm add AVGOUSDT 407.96 406.74        # multiple levels, one watch each
bfm monitor                           # stream alerts to this terminal
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
- Providers (`--provider`, or set `default_provider` in config): `telegram`,
  `stdout`, `file --file <path>`, `callback --callback-url <url>` (GET with
  `?message=...`). `bfm monitor` shows every alert regardless of provider.
- `--interval` sets the daemon poll cadence; applied when the daemon (re)starts.

## Develop / build from source

Run from source with [uv](https://docs.astral.sh/uv/) (config still lives at
`~/.config/bfm/config.toml`; override the dir with `BFM_CONFIG_DIR`):

```
uv sync
uv run ./src/main.py add DOGEUSDT 0.08285
```

Build the portable binary (pinned to Python 3.13; flags live in
`# nuitka-project:` comments in `src/main.py`):

```
uv run python scripts/build.py     # -> dist/bfm-<os>-<arch>
```

Releases are built per-OS by `.github/workflows/release.yml` on a `v*` tag.

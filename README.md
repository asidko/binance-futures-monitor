# binance-futures-monitor

[![ci](https://github.com/asidko/binance-futures-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/asidko/binance-futures-monitor/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/asidko/binance-futures-monitor)](https://github.com/asidko/binance-futures-monitor/releases/latest)
[![license: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

![demo](demo.gif)

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

**Android (Termux):** the same `curl ... | sh` line works - arm64 gets a prebuilt binary; other arches install from source (`pkg install python` first).

## Configure

`bfm` creates `~/.config/bfm/config.toml` on first run. For Telegram alerts, fill
it in:

```toml
default_provider = "telegram"   # telegram | stdout | file | callback | shell
default_condition = "closed"     # default when --condition omitted (empty = crosses + closed)

[telegram]
bot_token = "123456:abc..."
chat_id = "987654321"
```

Leave it empty and alerts default to stdout, which you watch live with `bfm monitor`.

## Use

```
bfm add DOGEUSDT 0.08285        # add a watch: symbol then level(s)
bfm add AVGOUSDT 407.96 406.74  # several levels at once, one watch each
bfm monitor                     # stream alerts live to this terminal
bfm list                        # list active watches
bfm status                      # daemon state + last poll time
bfm remove --symbol DOGEUSDT    # remove every watch for a symbol
bfm logs --follow               # tail the daemon log
bfm stop                        # stop the background daemon
```

Same `add` with explicit flags instead of the positional shorthand:

```
bfm add --symbol ETHUSDT --level 3500 --condition closed-above   # spell names out + pin one condition
```

`--condition` is repeatable and takes an exact condition or an alias. The six
exact conditions:

- `crosses-above` / `crosses-below` - last price ticks up / down through the level
- `closed-above` / `closed-below` - a candle closes above / below the level
- `closed-green` / `closed-red` - a candle closes green / red (level ignored)

Or an alias, which `bfm` resolves to one of the above from the current state when
you add the watch (`list` shows what it picked):

- `closed` -> `closed-above` or `closed-below`, whichever side price must move to reach the level
- `crosses` -> `crosses-above` or `crosses-below`, same rule
- `above` -> both `closed-above` and `crosses-above`
- `below` -> both `closed-below` and `crosses-below`
- `closed-opposite` -> `closed-green` or `closed-red`, opposite the last closed candle (a reversal alert)

For example `bfm add --symbol BTCUSDT --level 65000 --timeframe 1h --condition closed`.
Omit `--condition` and `bfm` uses `default_condition` from config; by default
that is `crosses` + `closed` (direction auto-picked).

- Providers (`--provider`, or set `default_provider` in config): `telegram`,
  `stdout`, `file --file <path>`, `callback --callback-url <url>` (GET with
  `?message=...`), `shell --notify-shell-command <cmd>` (runs the command via
  `/bin/sh`, `%s` = the message; omit the flag to use `notify_shell_command` from
  config - see the config comment for desktop-popup examples). `bfm monitor`
  shows every alert regardless of provider.
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
uv run python build.py     # -> dist/bfm-<os>-<arch>
```

Releases are built per-OS by `.github/workflows/release.yml` on a `v*` tag.

## License

MIT - see [LICENSE](LICENSE).

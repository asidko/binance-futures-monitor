# binance-futures-monitor

Read-only scripts to spot situations on Binance USD-M futures. One CLI drives a
single background daemon that watches many symbol+level pairs and alerts on
named conditions. Sources live in `src/`; shared logic in small libs.

## Setup

```
uv sync
cp .env.example .env   # fill TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
```

## How it works

`main.py` is both the CLI and (via an internal flag) the daemon. The
watchlist lives in SQLite at `.monitor-data/watches.db` - the CLI writes it, the
daemon reads it each poll cycle. `add` spawns the daemon if it isn't running;
the daemon auto-exits when the watchlist empties. Cross-side and last-candle
state are persisted, so a restart never re-fires or misses a flip.

Run every command with `uv run ./src/main.py <command>`.

## Commands

```
uv run ./src/main.py add --symbol DOGEUSDT --level 0.08285
uv run ./src/main.py add --symbol BTCUSDT --level 65000 --timeframe 1h --condition closed-above --condition closed-below
uv run ./src/main.py list
uv run ./src/main.py status
uv run ./src/main.py remove --id 3
uv run ./src/main.py remove --symbol DOGEUSDT
uv run ./src/main.py logs --follow
uv run ./src/main.py stop
```

- `add` with no `--condition` => auto: below the level watches `*above`, at/above watches `*below` (resolved at the daemon's first look, then fixed).
- Conditions: `crosses-above`, `crosses-below`, `closed-above`, `closed-below`.
- `--interval` sets the daemon poll cadence; it applies when the daemon (re)starts.

## Layout

- `src/main.py` - the only CLI: subcommands + daemon spawn.
- `src/daemon.py` - poll loop (lib).
- `src/store.py` - SQLite watchlist + dedup state + heartbeat (lib).
- `src/proclock.py` - flock-based single-instance lock + liveness (lib).
- `src/paths.py` - runtime paths, anchored to repo root (lib).
- `src/conditions.py`, `binance_client.py`, `config.py`, `notifier.py` - libs.
- `.monitor-data/` (gitignored): `watches.db`, `daemon.pid`, `daemon.log`. Override the dir with `BFM_DATA_DIR`.

## Notes / accepted limits

- Liveness is respawn-on-CLI-only (no systemd): if the daemon dies while idle it stays down until the next `add`/`start`. `status` reports UP/DOWN/WEDGED (exit 3 when down) so you can see it.
- Uses Last price (matches a line drawn on the chart), not Mark.
- A cycle reads the latest CLOSED candle; if `--interval` > timeframe, intermediate `closed-*` candles can be missed (`add` warns).
- REST polling, not websocket; cross detection is only as fine as `--interval`.

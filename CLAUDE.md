# binance-futures-monitor - project rules

Read-only scripts to spot situations on Binance USD-M futures. One CLI (`src/main.py`) drives a single background daemon; everything else is an imported lib. Sources in `src/`.

## Process
- Be patient: understand the use case and discuss trade-offs before architecting or writing files. Plan first; do not rush to code on a half-specified ask.

## Architecture
- Sources live in `src/`; run via `uv run ./src/main.py <command>` (sys.path[0] = src/, so flat sibling imports work; no packaging).
- `src/main.py` is the ONLY CLI tool (subcommands + daemon spawn). Everything else is a lib, imported only: `daemon.py`, `store.py`, `proclock.py`, `paths.py`, `conditions.py`, `binance_client.py`, `config.py`, `notifier.py`. Libs have no argparse/shebang/`__main__`.
- The CLI tool holds ZERO reusable logic: parse args, call lib, render. Wire by importing, never subprocess - the ONE exception is the daemon re-spawning itself detached.
- One file = one responsibility.
- No magic literals for shared conventions: name a constant in the module that owns it AND place it next to what it describes - not orphaned at the top (e.g. `CONDITION_AUTO_ABOVE_SUFFIX` right above the `REGISTRY` whose keys follow it). Never sprinkle a bare `"-above"`.
- `paths.py` is the single source of truth for all runtime locations (root, `.env`, db, pidfile, log), anchored to the repo root (parent of `src/`); override the data dir with `BFM_DATA_DIR`.

## CLI conventions (the one CLI tool)
- Shebang `#!/usr/bin/env python3`, `chmod +x`, `main() -> int`, `sys.exit(main())`.
- Subcommands via argparse subparsers; bare run (no args) prints help, exits 0. Header docstring drives `--help`: `description = __doc__` summary line, `epilog` = the Examples block, `RawDescriptionHelpFormatter`. Friendly `metavar="<x>"`.
- Mutually exclusive choices use a group (e.g. remove `--id` | `--symbol`, required). Fail fast with clear errors and exit codes: 0 ok, 1 config/runtime, 2 usage, 3 daemon-down.

## Daemon
- `main.py _daemon` runs the poll loop; the CLI spawns it detached (`start_new_session`, stdio to DEVNULL) on `add`/`start` if not already running.
- Liveness is flock-based, NOT `os.kill(pid,0)` (immune to PID reuse): the pidfile IS the lock (`proclock.DaemonLock`); the daemon holds it for life, `running_pid()` probes by trying to acquire. The daemon acquires the lock as its FIRST action and exits if it can't (lost the spawn race).
- Handle SIGTERM/SIGINT: set a stop flag, finish the cycle, release the lock. `stop` sends SIGTERM, polls, escalates to SIGKILL.
- Watchlist + comms live in SQLite (`store.py`); the store IS the CLI<->daemon channel (no socket). WAL + `busy_timeout` + `synchronous=NORMAL` on every connection. Add is atomically idempotent via `UNIQUE(...)` + `INSERT ON CONFLICT DO NOTHING`; conditions stored as canonical sorted JSON.
- Re-read the store each cycle (live add/remove). Auto-exit after N empty cycles (grace, so a concurrent add is seen first).
- Dedup state (cross side, last candle open_time) is PERSISTED per watch (`watch_state`) and reloaded on start - respawn-only makes restarts frequent, so in-memory dedup would miss or duplicate alerts.
- Liveness gap is accepted (respawn-on-CLI-only): `status` reports UP/DOWN/WEDGED (stale `last_cycle` = WEDGED), exit 3 when down. Daemon stamps `last_cycle` each cycle and logs via RotatingFileHandler.

## Tooling and secrets
- uv for everything: `uv sync`, `uv add <pkg>`, `uv run ./src/main.py`.
- Single global `.env` at the repo root for ALL scripts (gitignored; commit `.env.example`, kept key-synced). Never hardcode tokens. Load via `config.load_env()` at the entrypoint (anchored to root via `paths.ENV`, CWD-independent). Libs read `os.environ`.
- Long-running loop: `logging` with timestamps; catch per-iteration errors, log, keep looping; isolate per-symbol failures so one bad symbol never kills the cycle.

## Binance specifics
- Base `https://fapi.binance.com` (USD-M futures), read-only, `timeout` on every call.
- Fetch ALL prices in one call (`get_all_prices`, flat weight) - scales to any N; klines per unique (symbol, timeframe). Handle 418/429 with backoff.
- Last closed kline = `klines[-2]` (`[-1]` still forming). Use Last price for chart levels; Mark only when explicitly needed.
- Validate symbols against `/exchangeInfo` at add-time.

## Conditions
- Named registry; one interface `check(ctx, level, state) -> bool`, dedup state owned inside the condition.
- First observation sets a baseline and does NOT fire. One alert per event: cross = per side flip, close = per candle.
- Add a condition = one function + one `REGISTRY` row.
- Auto-select: below level picks all `*above`, at/above picks all `*below` (suffix-driven `auto_conditions()`). Resolved at the daemon's FIRST eval of a watch (price snapshot then) and persisted as concrete names - NOT at add-time (price can move before the daemon sees it).

## Notifier
- Providers are a dict registry; importable `notify(message, provider)`. Add a provider = one `_send_x` function + one `_PROVIDERS` row.

## New-file checklist
- [ ] CLI tool or lib? Only `main.py` is a CLI; new behavior is almost always a lib.
- Lib: no argparse/shebang/`__main__`; import-only docstring with a usage snippet.
- [ ] Verify: synthetic logic test (stub `notify`) + one live daemon smoke test in an isolated `BFM_DATA_DIR` before claiming done.

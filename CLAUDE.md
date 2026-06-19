# binance-futures-monitor - project rules

Read-only scripts to spot situations on Binance USD-M futures. Modular: self-contained CLI tools, shared logic in small libs.

## Process
- Be patient: understand the use case and discuss trade-offs before architecting or writing files. Plan first; do not rush to code on a half-specified ask.

## Architecture
- Two kinds of file, decided by who invokes it:
  - CLI tools - run directly by a human or cron: `monitor.py`, `notifier.py` (notifier is also importable). Follow the CLI conventions below.
  - Libs - imported only, never run: `binance_client.py`, `conditions.py`. No argparse, no shebang, no `__main__`.
- Decide tool vs lib up front: a human/cron runs it -> tool; only other code imports it -> lib. Do NOT bolt a CLI on a lib for "consistency" - that is ceremony.
- Reusable logic lives in libs. CLI tools hold ZERO reusable logic: parse args, call lib, render.
- Wire tools together by importing, never by subprocess (monitor imports `notify`, does not shell out to notifier.py).
- One file = one responsibility.
- No magic literals for shared conventions: name a constant in the module that owns it AND place it next to what it describes - not orphaned at the top (e.g. `CONDITION_AUTO_ABOVE_SUFFIX` right above the `REGISTRY` whose keys follow it). Never sprinkle a bare `"-above"` across code.

## CLI conventions (CLI tools only, not libs)
- Shebang `#!/usr/bin/env python3`, `chmod +x`.
- `--help` works; bare run (no args) prints help and exits 0:
  ```python
  if len(sys.argv) == 1:
      parser.print_help()
      return 0
  ```
- `main() -> int`, `sys.exit(main())`.
- Header docstring drives `--help`. To avoid a DOUBLE "options" block, do NOT feed the whole docstring as description:
  ```python
  parser = argparse.ArgumentParser(
      description=__doc__.strip().splitlines()[0],          # summary line only
      epilog=__doc__[__doc__.index("Examples:"):].rstrip(), # examples block
      formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  ```
  Options render once from native `help=` on each arg. Use friendly `metavar="<x>"`.

## Docstring headers
CLI tool format:
```
toolname.py - one-line description.

Usage: ./toolname.py --foo <x> [--bar <y>]

Options:
  --foo <x>   What it is.
  --bar <y>   What it is (default: ...).

Examples:
  ./toolname.py --foo a
  ./toolname.py --foo a --bar b
```
- Compact description only - no "Why:" essays.
- Simple example first (common manual use), then extended. Single-flag tools get one example; do not fake depth.

Lib format: one-line description, "Library module, not a CLI.", then an import snippet.

## Tooling and secrets
- uv for everything: `uv sync`, `uv add <pkg>`, `uv run ./tool.py`.
- Single global `.env` at the repo root holds secrets for ALL scripts (gitignored; commit `.env.example`). Never hardcode tokens.
- Keep `.env.example` key-synced with `.env`: every key in one exists in the other; the example holds placeholders/blanks only, never real values. Add a key -> add it to both.
- Load it via `config.load_env()` at each tool's entrypoint - never bare `load_dotenv()`. `config.py` anchors `.env` to the repo root (`Path(__file__).parent`), so it loads regardless of CWD (cron-safe). Libs read `os.environ`; only entrypoints load.
- Long-running loops: `logging` with timestamps, not print. Catch per-iteration errors, log, keep looping.

## Binance specifics
- Base `https://fapi.binance.com` (USD-M futures), read-only public endpoints, `timeout` on every call.
- Last closed kline = `klines[-2]` (`[-1]` is the still-forming candle).
- Use Last price for levels drawn on the chart; Mark price only when explicitly needed.

## Conditions
- Named registry; one interface `check(ctx, level, state) -> bool`, dedup state owned inside the condition.
- First observation sets a baseline and does NOT fire (no stale alert on startup).
- One alert per event: cross = per side flip, close = per candle.
- Add a condition = one function + one `REGISTRY` row.
- Auto-select (`--condition-auto`, monitor default): from launch price - below level picks all `*above`, at/above picks all `*below`. Suffix-driven in `auto_conditions()`, so new directional conditions are picked up free. Startup snapshot, not re-evaluated per poll.

## Notifier
- Providers are a dict registry; importable `notify(message, provider)` plus a CLI.
- Add a provider = one `_send_x` function + one `_PROVIDERS` row.

## New-file checklist
- [ ] Decide first: CLI tool (run directly) or lib (imported only)? Do not CLI-ify a lib.
- CLI tool: self-contained, shebang + executable; `--help` + bare-run-prints-help; header docstring (desc / Usage / Options / Examples); zero reusable logic (lives in a lib).
- Lib: no argparse/shebang/`__main__`; import-only docstring with a usage snippet.
- [ ] Verify: synthetic logic test + one live probe before claiming done.

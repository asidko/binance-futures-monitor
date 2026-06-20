"""config.py - load the global TOML config shared by all scripts.

Library module, not a CLI. Reads ~/.config/bfm/config.toml (see paths), creating
it from defaults on first use. Values are exported into os.environ so libs keep
reading os.environ; only non-empty values are set, so a real shell env still wins.

  import config; config.load()
"""
import os
import tomllib

import paths

_DEFAULT = """\
# bfm config. Real file lives at ~/.config/bfm/config.toml (auto-created).
# Fill in Telegram to push alerts there; otherwise alerts fall back to stdout
# (watch them live with `bfm monitor`).

# default provider when --provider is omitted: "telegram" | "stdout" | "file" | "callback"
default_provider = ""

[telegram]
bot_token = ""
chat_id = ""
"""


def ensure_config() -> None:
    if not paths.CONFIG_FILE.exists():
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        paths.CONFIG_FILE.write_text(_DEFAULT)


def load() -> None:
    ensure_config()
    try:
        with open(paths.CONFIG_FILE, "rb") as f:
            cfg = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"error: invalid config at {paths.CONFIG_FILE}: {exc}")
    telegram = cfg.get("telegram", {})
    _export("TELEGRAM_BOT_TOKEN", telegram.get("bot_token"))
    _export("TELEGRAM_CHAT_ID", telegram.get("chat_id"))
    _export("DEFAULT_PROVIDER", cfg.get("default_provider"))


def _export(key: str, value) -> None:
    if value and key not in os.environ:
        os.environ[key] = str(value)

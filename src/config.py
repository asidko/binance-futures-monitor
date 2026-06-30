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

# default provider when --provider is omitted: "telegram" | "stdout" | "file" | "callback" | "shell"
default_provider = ""

# command the shell provider runs (%s = the alert message, %% = a literal %);
# used when --notify-shell-command is omitted. Runs via /bin/sh, so $HOME etc.
# expand. Quote %s - the message has spaces and parentheses.
#   default     notify_shell_command = 'echo "%s" >> $HOME/bfm_notifications.txt'
#   macOS popup notify_shell_command = 'terminal-notifier -title "bfm" -message "%s"'
#   Linux popup notify_shell_command = 'notify-send "bfm" "%s"'
notify_shell_command = ""

# default conditions when --condition is omitted: a family ("closed" | "crosses"
# auto-pick direction; "above" | "below"), "closed-opposite" (color flip of the
# last closed candle), or a full name ("closed-above" | "closed-green").
# Comma-separated for several. Empty = both crosses and closed (auto direction).
default_condition = ""

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
    _export("DEFAULT_CONDITION", cfg.get("default_condition"))
    _export("NOTIFY_SHELL_COMMAND", cfg.get("notify_shell_command"))


def _export(key: str, value) -> None:
    if value and key not in os.environ:
        os.environ[key] = str(value)

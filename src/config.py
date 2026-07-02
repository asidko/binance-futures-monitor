"""config.py - load the global TOML config shared by all scripts.

Library module, not a CLI. Reads ~/.config/bfm/config.toml (see paths), creating
it from defaults on first use and re-syncing it to the current template on every
run (filled values kept, missing keys added with defaults, comments refreshed).
Values are exported into os.environ so libs keep reading os.environ; only
non-empty values are set, so a real shell env still wins.

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
#   default      notify_shell_command = 'echo "%s" >> $HOME/bfm_notifications.txt'
#   macOS native notify_shell_command = "osascript -e 'display notification \"%s\" with title \"bfm\"'"  # zero install
#   macOS popup  notify_shell_command = 'terminal-notifier -title "bfm" -message "%s"'  # needs: brew install terminal-notifier
#   Linux popup  notify_shell_command = 'notify-send "bfm" "%s"'
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
    paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not paths.CONFIG_FILE.exists():
        _write_atomic(_DEFAULT, 0o600)  # will hold telegram tokens; owner-only
    else:
        _sync()


def _sync() -> None:
    current = paths.CONFIG_FILE.read_text()
    try:
        values = tomllib.loads(current)
    except tomllib.TOMLDecodeError:
        return
    merged = _render(values)
    if merged == current:
        return
    try:
        tomllib.loads(merged)  # never overwrite a valid config with invalid TOML
    except tomllib.TOMLDecodeError:
        return
    _write_atomic(merged, paths.CONFIG_FILE.stat().st_mode & 0o777)


def _write_atomic(content: str, mode: int) -> None:
    """tmp is pid-unique (CLI and daemon both sync at startup) and created with
    the final mode up front, so a token never sits in a group-readable file."""
    tmp = paths.CONFIG_FILE.with_name(f"{paths.CONFIG_FILE.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)
    os.chmod(tmp, mode)  # O_CREAT mode is masked by umask; assert it exactly
    tmp.replace(paths.CONFIG_FILE)


def _render(values: dict) -> str:
    """Re-emit the template, overlaying each key's value from `values` when set;
    missing keys keep their template default. Comments/structure follow _DEFAULT."""
    section = None
    out = []
    for line in _DEFAULT.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
        elif stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            container = values.get(section, {}) if section else values
            if isinstance(container, dict) and key in container:
                try:
                    out.append(f"{key} = {_toml_value(container[key])}")
                    continue
                except TypeError:
                    pass
        out.append(line)
    return "\n".join(out) + "\n"


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        raise TypeError(f"non-scalar config value: {type(value).__name__}")
    escaped = (value.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return f'"{escaped}"'


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

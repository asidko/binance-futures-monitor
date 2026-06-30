"""notifier.py - send an alert message through a pluggable provider.

Library module, not a CLI. Providers are a dict registry; add one = a _send_x
function plus a REGISTRY row. The file provider takes a path via `arg`;
stdout is a no-op here (alerts reach the terminal via `bfm monitor`); the shell
provider runs `arg` with `%s` replaced by the message.

  from notifier import notify
  notify("[DOGE] level broke", "telegram")
  notify("[DOGE] level broke", "file", "/tmp/alerts.log")
  notify("[DOGE] level broke", "shell", 'terminal-notifier -message "%s"')
"""
import os
import subprocess
from dataclasses import dataclass
from typing import Callable

import requests

TELEGRAM_API = "https://api.telegram.org"


def telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _send_telegram(message: str, arg: str | None) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
    resp = requests.post(
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=10,
    )
    resp.raise_for_status()


def _send_file(message: str, arg: str | None) -> None:
    if not arg:
        raise RuntimeError("file provider needs an output path")
    with open(arg, "a") as f:
        f.write(message + "\n")


def _send_stdout(message: str, arg: str | None) -> None:
    pass


def _send_callback(message: str, arg: str | None) -> None:
    if not arg:
        raise RuntimeError("callback provider needs a URL")
    resp = requests.get(arg, params={"message": message}, timeout=10)
    resp.raise_for_status()


def _send_shell(message: str, arg: str | None) -> None:
    if not arg:
        raise RuntimeError("shell provider needs a command (use %s for the message)")
    cmd = arg.replace("%%", "\0").replace("%s", message).replace("\0", "%")
    subprocess.run(cmd, shell=True, check=True, timeout=10)


def _validate_file(path: str) -> str:
    full = os.path.abspath(path)
    try:
        with open(full, "a"):
            pass
    except OSError as exc:
        raise ValueError(f"cannot write to {full}: {exc}")
    return full


def _validate_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        raise ValueError("callback URL must start with http:// or https://")
    return url


def _validate_shell(cmd: str) -> str:
    if not cmd.strip():
        raise ValueError("shell command must not be empty")
    return cmd


@dataclass
class Provider:
    send: Callable[[str, str | None], None]
    arg_flag: str | None = None  # CLI flag a watch must supply; None = no arg
    arg_dest: str | None = None  # argparse dest holding that flag's value
    validate: Callable[[str], str] | None = None  # normalize the arg or raise ValueError
    arg_env: str | None = None  # config-supplied default for the arg when the flag is omitted


REGISTRY = {
    "telegram": Provider(_send_telegram),
    "file": Provider(_send_file, "--file <path>", "file", _validate_file),
    "stdout": Provider(_send_stdout),
    "callback": Provider(_send_callback, "--callback-url <url>", "callback", _validate_url),
    "shell": Provider(_send_shell, "--notify-shell-command <cmd>", "shell_command", _validate_shell, "NOTIFY_SHELL_COMMAND"),
}

PROVIDERS = tuple(REGISTRY)


def notify(message: str, provider: str, arg: str | None = None) -> None:
    spec = REGISTRY.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider '{provider}' (have: {', '.join(REGISTRY)})")
    spec.send(message, arg)

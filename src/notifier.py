"""notifier.py - send an alert message through a pluggable provider.

Library module, not a CLI. Providers are a dict registry; add one = a _send_x
function plus a _PROVIDERS row. The file provider takes a path via `arg`;
stdout is a no-op here (alerts reach the terminal via `bfm monitor`).

  from notifier import notify
  notify("[DOGE] level broke", "telegram")
  notify("[DOGE] level broke", "file", "/tmp/alerts.log")
"""
import os
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


@dataclass
class Provider:
    send: Callable[[str, str | None], None]
    arg_flag: str | None = None  # CLI flag a watch must supply; None = no arg
    validate: Callable[[str], str] | None = None  # normalize the arg or raise ValueError


REGISTRY = {
    "telegram": Provider(_send_telegram),
    "file": Provider(_send_file, "--file <path>", _validate_file),
    "stdout": Provider(_send_stdout),
    "callback": Provider(_send_callback, "--callback-url <url>", _validate_url),
}

PROVIDERS = tuple(REGISTRY)


def notify(message: str, provider: str, arg: str | None = None) -> None:
    spec = REGISTRY.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider '{provider}' (have: {', '.join(REGISTRY)})")
    spec.send(message, arg)

"""notifier.py - send an alert message through a pluggable provider (telegram for now).

Library module, not a CLI.

  from notifier import notify
  notify("[DOGE] level broke", provider="telegram")
"""
import os

import requests


def _send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=10,
    )
    resp.raise_for_status()


_PROVIDERS = {
    "telegram": _send_telegram,
}


def notify(message: str, provider: str = "telegram") -> None:
    sender = _PROVIDERS.get(provider)
    if sender is None:
        raise ValueError(f"unknown provider '{provider}' (have: {', '.join(_PROVIDERS)})")
    sender(message)

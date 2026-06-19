#!/usr/bin/env python3
"""notifier.py - send an alert message through a pluggable provider (telegram for now).

Usage: ./notifier.py --message <text> [--provider <provider>]

Options:
  --message <text>        Message to send.
  --provider <provider>   Notification provider (default: telegram).

Examples:
  ./notifier.py --message "[DOGE] Kline closed ABOVE the level"
  ./notifier.py --message "Service restarted" --provider telegram
"""
import argparse
import os
import sys

import requests

import config


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        epilog=__doc__[__doc__.index("Examples:"):].rstrip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--message", metavar="<text>", required=True, help="Message to send.")
    parser.add_argument("--provider", metavar="<provider>", default="telegram", choices=list(_PROVIDERS),
                        help="Notification provider (default: telegram).")
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    args = parser.parse_args()

    config.load_env()
    notify(args.message, args.provider)
    print(f"sent via {args.provider}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

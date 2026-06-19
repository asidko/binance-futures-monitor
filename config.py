"""config.py - load the project-global .env shared by all scripts.

Library module, not a CLI. Anchors .env to the repo root so it loads
regardless of the current working directory (cron-safe).

  import config
  config.load_env()  # call once at a tool's entrypoint
"""
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def load_env() -> None:
    load_dotenv(_ENV_PATH)

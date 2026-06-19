"""config.py - load the project-global .env shared by all scripts.

Library module, not a CLI. Anchored to the repo root via paths.ENV, so it
loads regardless of CWD (cron/daemon-safe).

  import config; config.load_env()
"""
from dotenv import load_dotenv

import paths


def load_env() -> None:
    load_dotenv(paths.ENV)

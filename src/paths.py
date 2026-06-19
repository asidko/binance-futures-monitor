"""paths.py - single source of truth for project and runtime file locations.

Library module, not a CLI. Anchored to the repo root (parent of src/), so
every tool resolves the same paths regardless of CWD.

  import paths
  paths.ensure_data_dir(); db = paths.DB
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

DATA_DIR = Path(os.environ.get("BFM_DATA_DIR") or (ROOT / ".monitor-data"))
DB = DATA_DIR / "watches.db"
PIDFILE = DATA_DIR / "daemon.pid"
LOG = DATA_DIR / "daemon.log"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

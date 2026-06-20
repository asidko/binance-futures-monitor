"""paths.py - single source of truth for project and runtime file locations.

Library module, not a CLI. Everything lives in one dir, ~/.config/bfm (XDG):
config.toml, watches.db, daemon.pid, daemon.log. Resolves the same regardless of
CWD. Override the dir with BFM_CONFIG_DIR.

  import paths
  paths.ensure_data_dir(); db = paths.DB
"""
import os
import sys
from pathlib import Path

# Nuitka does not set sys.frozen; it injects __compiled__ into __main__ with the
# real binary path (original_argv0), valid even when invoked relative or via PATH.
_compiled = getattr(sys.modules.get("__main__"), "__compiled__", None)
FROZEN = _compiled is not None
EXECUTABLE = Path(_compiled.original_argv0).resolve() if FROZEN else None

_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
CONFIG_DIR = Path(os.environ.get("BFM_CONFIG_DIR") or (_CONFIG_HOME / "bfm"))
CONFIG_FILE = CONFIG_DIR / "config.toml"

DATA_DIR = CONFIG_DIR
DB = DATA_DIR / "watches.db"
PIDFILE = DATA_DIR / "daemon.pid"
LOG = DATA_DIR / "daemon.log"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

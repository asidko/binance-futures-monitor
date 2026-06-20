"""paths.py - single source of truth for project and runtime file locations.

Library module, not a CLI. Everything lives in one dir, ~/.config/bfm (XDG):
config.toml, watches.db, daemon.pid, daemon.log. Resolves the same regardless of
CWD. Override the dir with BFM_CONFIG_DIR.

  import paths
  paths.ensure_data_dir(); db = paths.DB
"""
import os
import shutil
import sys
from pathlib import Path


def _resolve_executable(argv0: str) -> Path:
    """The real onefile binary, for re-spawning the daemon. original_argv0 is
    argv[0] as invoked: a bare name (PATH lookup) must go through which(), or it
    would resolve against CWD (e.g. `bfm` -> ./bfm)."""
    if os.sep in argv0 or (os.altsep and os.altsep in argv0):
        return Path(argv0).resolve()
    found = shutil.which(argv0)
    return Path(found).resolve() if found else Path(argv0).resolve()


# Nuitka does not set sys.frozen; it injects __compiled__ into __main__, exposing
# the invocation path as original_argv0.
_compiled = getattr(sys.modules.get("__main__"), "__compiled__", None)
FROZEN = _compiled is not None
EXECUTABLE = _resolve_executable(_compiled.original_argv0) if FROZEN else None

_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
CONFIG_DIR = Path(os.environ.get("BFM_CONFIG_DIR") or (_CONFIG_HOME / "bfm"))
CONFIG_FILE = CONFIG_DIR / "config.toml"

DATA_DIR = CONFIG_DIR
DB = DATA_DIR / "watches.db"
PIDFILE = DATA_DIR / "daemon.pid"
LOG = DATA_DIR / "daemon.log"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

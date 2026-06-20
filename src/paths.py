"""paths.py - single source of truth for project and runtime file locations.

Library module, not a CLI. Run from source it anchors to the repo root (parent
of src/); as an installed binary it anchors to the per-user dir ~/.bfm, so a
binary on PATH (e.g. ~/.local/bin) never litters its own dir with .env or a db.
Resolves the same regardless of CWD. Override the data dir with BFM_DATA_DIR.

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
if FROZEN:
    EXECUTABLE = Path(_compiled.original_argv0).resolve()
    ROOT = Path.home() / ".bfm"
else:
    EXECUTABLE = None
    ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

DATA_DIR = Path(os.environ.get("BFM_DATA_DIR") or (ROOT / ".monitor-data"))
DB = DATA_DIR / "watches.db"
PIDFILE = DATA_DIR / "daemon.pid"
LOG = DATA_DIR / "daemon.log"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

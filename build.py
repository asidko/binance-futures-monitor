#!/usr/bin/env python3
"""build.py - compile a portable single-file binary with Nuitka.

Run via `uv run python build.py`. Build flags live next to the code in
`src/main.py` (nuitka-project comments); this script only invokes Nuitka and
names the artifact per OS/arch. CI calls this exact command on each runner.
"""
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "src" / "main.py"
DIST = ROOT / "dist"

_OS = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}
_ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}


def _target() -> str:
    osname = _OS.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    arch = _ARCH.get(machine, machine)
    return f"bfm-{osname}-{arch}"


def main() -> int:
    cmd = [sys.executable, "-m", "nuitka", str(ENTRY)]
    print("building:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(ROOT))

    built = DIST / ("bfm.exe" if platform.system() == "Windows" else "bfm")
    if not built.exists():
        print(f"error: expected artifact missing at {built}", file=sys.stderr)
        return 1
    suffix = ".exe" if platform.system() == "Windows" else ""
    final = DIST / (_target() + suffix)
    built.replace(final)
    final.chmod(0o755)
    print("artifact:", final)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""proclock.py - flock-based single-instance lock + liveness, immune to PID reuse.

Library module, not a CLI. The pidfile IS the lock: the daemon holds an
exclusive flock for its whole life. A non-blocking acquire that SUCCEEDS means
no daemon holds it (none/stale); EWOULDBLOCK means a daemon is alive. This
survives SIGKILL (the OS drops the flock) and never false-positives on a
recycled PID.

  import proclock
  lock = proclock.DaemonLock(pidfile); lock.acquire()
  pid = proclock.running_pid(pidfile)  # live pid or None
"""
import errno
import fcntl
import os
from pathlib import Path


class DaemonLock:
    def __init__(self, pidfile: Path) -> None:
        self._pidfile = pidfile
        self._fd: int | None = None

    def acquire(self) -> bool:
        self._pidfile.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._pidfile, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EWOULDBLOCK, errno.EACCES):
                return False
            raise
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        os.fsync(fd)
        self._fd = fd
        return True

    def release(self) -> None:
        """Unlock and close, but never unlink: removing the path lets a probe
        lock the old inode while a new daemon locks a fresh file - two daemons.
        The pidfile is permanent; a dead holder just leaves it unlocked."""
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


def running_pid(pidfile: Path) -> int | None:
    if not pidfile.exists():
        return None
    fd = os.open(pidfile, os.O_RDONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            try:
                return int(pidfile.read_text().strip() or 0) or None
            except ValueError:
                return None
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return None
    finally:
        os.close(fd)

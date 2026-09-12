"""Cross-process lock for heavy publish operations.

Collect / purge / export / push all touch the same SQLite DB and the ``site/``
git worktree, so they must never run concurrently — not even across the Flask
app, ``start.py``'s scheduler and its background push-retry thread, or a manual
``python -m daily_push``.

Uses an OS advisory lock (``msvcrt`` on Windows, ``fcntl`` on POSIX) so a crash
never leaves a stale lock: the OS releases it when the process exits.
"""
import os
import time

try:  # Windows
    import msvcrt

    def _try_lock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
except ImportError:  # POSIX
    import fcntl

    def _try_lock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOCK = os.path.join(BASE_DIR, "data", ".publish.lock")


class LockBusy(RuntimeError):
    """Raised when the lock is held by another operation."""


class HeavyLock:
    def __init__(self, path=DEFAULT_LOCK, timeout=900):
        self.path = path
        self.timeout = timeout
        self._fh = None

    def acquire(self, blocking=True, timeout=None):
        timeout = self.timeout if timeout is None else timeout
        deadline = time.time() + timeout
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        self._fh = open(self.path, "a+")
        while True:
            try:
                _try_lock(self._fh)
                return self
            except OSError:
                if not blocking or time.time() >= deadline:
                    self._fh.close()
                    self._fh = None
                    raise LockBusy(f"另一个任务正在运行（{self.path}）")
                time.sleep(0.5)

    def release(self):
        if self._fh is None:
            return
        try:
            _unlock(self._fh)
        except OSError:
            pass
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


def heavy_lock(timeout=900, path=None):
    return HeavyLock(path or DEFAULT_LOCK, timeout=timeout)

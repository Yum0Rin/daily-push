"""Cross-process publish lock behavior."""
import os
import tempfile
import unittest

from daily_push.publish_lock import HeavyLock, LockBusy, heavy_lock


class PublishLockTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), ".publish.lock")

    def test_acquire_release(self):
        a = HeavyLock(self.path)
        a.acquire(blocking=False)
        a.release()
        b = HeavyLock(self.path)
        b.acquire(blocking=False)
        b.release()

    def test_second_acquire_is_busy(self):
        a = HeavyLock(self.path)
        a.acquire(blocking=False)
        try:
            with self.assertRaises(LockBusy):
                HeavyLock(self.path).acquire(blocking=False)
        finally:
            a.release()
        # released -> acquirable again
        c = HeavyLock(self.path)
        c.acquire(blocking=False)
        c.release()

    def test_context_manager(self):
        with heavy_lock(path=self.path):
            pass


if __name__ == "__main__":
    unittest.main()

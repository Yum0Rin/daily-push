"""apply_history: backfill comment/favorite counts, then drop over-threshold songs."""
import tempfile
import unittest

from daily_push.netease_history import apply_history
from daily_push.storage import Storage


class ApplyHistoryTest(unittest.TestCase):
    def test_backfill_and_filter(self):
        d = tempfile.mkdtemp()
        st = Storage(d)
        st.save("2026-01-01", netease=[
            {"id": 1, "name": "A"},                                            # no counts
            {"id": 2, "name": "B"},                                            # no counts, over limit
            {"id": 3, "name": "C", "comment_count": 100, "favorite_count": 50},  # already has counts
        ], overwrite=True)
        st.close()

        calls = []

        def stats(sid):
            calls.append(sid)
            return {1: (5000, 1000), 2: (20000, 2000)}.get(sid, (None, None))

        st2 = Storage(d)
        res = apply_history(st2, 10000, 0, stats, 0)
        row = st2.get("2026-01-01")
        st2.close()

        self.assertEqual(res["backfilled"], 2)
        self.assertEqual([r[1] for r in res["removed"]], ["B"])
        self.assertEqual([s["id"] for s in row["netease"]], [1, 3])
        self.assertEqual(row["netease"][0]["comment_count"], 5000)
        self.assertEqual(row["netease"][0]["favorite_count"], 1000)
        self.assertNotIn(3, calls)  # entry already had counts -> no lookup

    def test_zero_threshold_backfills_but_keeps_all(self):
        d = tempfile.mkdtemp()
        st = Storage(d)
        st.save("2026-01-02", netease=[{"id": 9, "name": "X"}], overwrite=True)
        st.close()

        st2 = Storage(d)
        res = apply_history(st2, 0, 0, lambda sid: (99999, 123), 0)
        row = st2.get("2026-01-02")
        st2.close()
        self.assertEqual(res["backfilled"], 1)
        self.assertEqual(res["removed"], [])
        self.assertEqual(row["netease"][0]["comment_count"], 99999)
        self.assertEqual(row["netease"][0]["favorite_count"], 123)


if __name__ == "__main__":
    unittest.main()

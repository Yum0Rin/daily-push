"""Netease: skip songs whose comment count exceeds the threshold, fill to max_songs."""
import unittest

from daily_push.sources.netease import _NeteaseHttp


class NeteaseCommentFilterTest(unittest.TestCase):
    def _collector(self, max_songs, max_comments):
        cfg = {"max_songs": max_songs,
               "netease": {"cookie": "MUSIC_U=x", "max_comments": max_comments}}
        c = _NeteaseHttp(cfg)
        songs = [{"id": i, "name": f"S{i}", "ar": [], "al": {}, "dt": 1} for i in range(1, 7)]
        totals = {1: 5000, 2: 20000, 3: 3000, 4: 40000, 5: 100, 6: 99999}

        def fake_get(path, params=None):
            if path == "/recommend/songs":
                return {"code": 200, "data": {"dailySongs": songs}}
            if path == "/comment/music":
                sid = params["id"]
                return {"code": 200, "total": totals.get(sid, 0),
                        "hotComments": [{"content": f"hot{sid}"}]}
            raise AssertionError(path)

        c._get = fake_get
        return c

    def test_skips_high_comment_and_fills(self):
        out = self._collector(max_songs=3, max_comments=10000).collect()
        self.assertEqual([s["id"] for s in out], [1, 3, 5])
        self.assertEqual(out[0]["hot_comment"], "hot1")

    def test_zero_means_no_limit(self):
        out = self._collector(max_songs=3, max_comments=0).collect()
        self.assertEqual([s["id"] for s in out], [1, 2, 3])

    def test_not_enough_passing_returns_what_it_has(self):
        out = self._collector(max_songs=5, max_comments=10000).collect()
        self.assertEqual([s["id"] for s in out], [1, 3, 5])


if __name__ == "__main__":
    unittest.main()

"""pipeline.run_once: collect → export → push, stop before publish on error."""
import unittest
from unittest import mock

from daily_push import pipeline


class RunOnceTest(unittest.TestCase):
    def test_collect_error_stops_before_publish(self):
        with mock.patch("daily_push.collector.collect_once",
                        return_value={"push_date": "2026-01-01", "mp": {"error": "boom"}}), \
                mock.patch("daily_push.export_site.export_site") as exp, \
                mock.patch("daily_push.export_site.push_site") as push, \
                mock.patch("daily_push.pipeline.run_status.record") as rec:
            out = pipeline.run_once()
        self.assertEqual(out["errors"], {"mp": "boom"})
        self.assertIsNone(out["exported"])
        exp.assert_not_called()
        push.assert_not_called()
        rec.assert_not_called()

    def test_success_exports_and_pushes(self):
        with mock.patch("daily_push.collector.collect_once",
                        return_value={"push_date": "2026-01-01", "mp": []}), \
                mock.patch("daily_push.export_site.export_site",
                           return_value="/tmp/index.html"), \
                mock.patch("daily_push.export_site.push_site",
                           return_value="https://example/repo"), \
                mock.patch("daily_push.pipeline.run_status.record") as rec:
            out = pipeline.run_once()
        self.assertEqual(out["errors"], {})
        self.assertEqual(out["exported"], "/tmp/index.html")
        self.assertEqual(out["pushed"], "https://example/repo")
        self.assertIsNone(out["push_error"])
        self.assertEqual([c.args[0] for c in rec.call_args_list],
                         ["last_collect", "last_push"])

    def test_push_error_captured(self):
        with mock.patch("daily_push.collector.collect_once",
                        return_value={"push_date": "2026-01-01", "mp": []}), \
                mock.patch("daily_push.export_site.export_site",
                           return_value="/tmp/index.html"), \
                mock.patch("daily_push.export_site.push_site",
                           side_effect=RuntimeError("no repo")), \
                mock.patch("daily_push.pipeline.run_status.record") as rec:
            out = pipeline.run_once()
        self.assertEqual(out["push_error"], "no repo")
        self.assertEqual([c.args[0] for c in rec.call_args_list], ["last_collect"])


if __name__ == "__main__":
    unittest.main()

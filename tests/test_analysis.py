import unittest

from frontdoor_lab.analysis import correlate, decode_records


class CorrelationTests(unittest.TestCase):
    def test_adjacent_log_records_are_preserved(self):
        self.assertEqual(decode_records(' {"id": 1}{"id": 2}\n'), [{"id": 1}, {"id": 2}])
        self.assertEqual(decode_records("\n"), [])
        with self.assertRaises(ValueError):
            decode_records('{"id": 1}truncated')

    def test_cached_origin_id_is_not_a_new_origin_request(self):
        baseline = {"path": "/objects/run/etag-warm/v1.json", "request_id": "direct", "body_sha256": "body"}
        case = {
            "run": "run", "case": "etag", "requested_cache_state": "warm",
            "baseline": baseline, "warm_verified_before_request": True,
            "conditional": {"path": baseline["path"], "request_id": "conditional", "status": 304,
                            "headers": {"X-Cache": "TCP_HIT", "X-Lab-Origin-Id": "fill-origin"},
                            "body_bytes": 0, "body_sha256": "empty", "sent_headers": {}},
        }
        logs = [{"path": baseline["path"], "origin_id": "fill-origin", "status": 200,
                 "headers": {"X-Lab-Request-Id": ["fill"]}}]
        result = correlate(case, logs)
        self.assertEqual(result["origin_records"], [])
        self.assertEqual(result["baseline_origin_records"], 0)
        logs.append({"path": baseline["path"], "origin_id": "new-origin", "status": 200,
                     "headers": {"X-Lab-Request-Id": ["conditional"], "If-None-Match": None}})
        result = correlate(case, logs)
        self.assertEqual(result["origin_records"][0]["status"], 200)
        self.assertTrue(result["body_valid"])
        self.assertTrue(result["status_matches_fixture_condition"])


if __name__ == "__main__":
    unittest.main()

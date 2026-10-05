import contextlib
from http.server import ThreadingHTTPServer
import io
import gzip
from hashlib import sha256
import json
import threading
import unittest

from frontdoor_lab.origin import BODY, ETAG, LAST_MODIFIED, Origin, not_modified
from frontdoor_lab.probe import fetch, header, run


class ConditionalTests(unittest.TestCase):
    def test_matching_etag(self):
        self.assertTrue(not_modified({"If-None-Match": ETAG}))

    def test_weak_list_and_wildcard(self):
        for value in ("W/" + ETAG, '"other", W/' + ETAG, "*"):
            self.assertTrue(not_modified({"If-None-Match": value}))

    def test_precedence(self):
        self.assertFalse(not_modified({"If-None-Match": '"other"', "If-Modified-Since": LAST_MODIFIED}))

    def test_date_and_invalid_date(self):
        self.assertTrue(not_modified({"If-Modified-Since": LAST_MODIFIED}))
        self.assertFalse(not_modified({"If-Modified-Since": "not a date"}))
        self.assertFalse(not_modified({"If-Modified-Since": "Wed, 01 Jan 2020 00:00:00 GMT"}))

    def test_no_condition(self):
        self.assertFalse(not_modified({}))

    def test_gzip_keeps_raw_hash_and_validates_decoded_body(self):
        encoded = gzip.compress(BODY)

        class GzipOrigin(Origin):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        server = ThreadingHTTPServer(("127.0.0.1", 0), GzipOrigin)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = fetch(f"http://127.0.0.1:{server.server_port}", "/", {"Accept-Encoding": "gzip"})
            self.assertEqual(result["body_sha256"], sha256(encoded).hexdigest())
            self.assertEqual(result["decoded_body_sha256"], sha256(BODY).hexdigest())
            self.assertEqual(result["decoded_body_bytes"], len(BODY))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_http_and_probe_integration(self):
        # Loopback validates OUR harness, not Azure Front Door cache behaviour.
        server = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                first = fetch(base, "/objects/local/control/v1.json", {})
                self.assertEqual(first["body_bytes"], len(BODY))
                self.assertEqual(header(first, "ETag"), ETAG)
                second = fetch(base, "/objects/local/control/v1.json", {"If-None-Match": ETAG})
                self.assertEqual((second["status"], second["body_bytes"]), (304, 0))
                run(base, base, label="loopback-no-CDN", warm_attempts=0)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        cases = [row for row in records if "case" in row]
        self.assertEqual(len(cases), 12)
        paths = set()
        for row in cases:
            self.assertFalse(row["warm_verified_before_request"])
            response = row["conditional"]
            self.assertNotIn(response["path"], paths)
            paths.add(response["path"])
            expected = 200 if row["case"] in ("nonmatch", "precedence") else 304
            self.assertEqual(response["status"], expected)
            logs = [r for r in records if r.get("origin_id") and r["headers"].get("X-Lab-Request-Id") == [response["request_id"]]]
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["path"], response["path"])


if __name__ == "__main__":
    unittest.main()

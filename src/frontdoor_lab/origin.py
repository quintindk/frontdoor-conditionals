"""Synthetic conditional-GET origin. Not a production HTTP server or an AFD emulator."""
import argparse
from datetime import timezone
from email.utils import formatdate, parsedate_to_datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import time
import uuid


MODIFIED = 1759276800  # Fixed fixture timestamp; never changes on a cache hit.
BODY = json.dumps({"version": 1, "payload": "x" * 8000}).encode()
ETAG = '"' + sha256(BODY).hexdigest() + '"'
LAST_MODIFIED = formatdate(MODIFIED, usegmt=True)
HEADERS_TO_LOG = (
    "If-None-Match", "If-Modified-Since", "Accept-Encoding", "Range",
    "Cache-Control", "X-Lab-Request-Id", "X-Azure-Ref", "X-Azure-FDID",
)


def not_modified(headers):
    # GET uses weak ETag comparison. If-None-Match takes precedence over dates.
    value = headers.get("If-None-Match")
    if value is not None:
        return value.strip() == "*" or ETAG in re.findall(r'(?:W/)?("[^"]*")', value)
    value = headers.get("If-Modified-Since")
    if value:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return MODIFIED <= date.timestamp()
        except (ValueError, TypeError, OverflowError):
            pass
    return False


class Origin(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not re.fullmatch(r"/objects/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/v1\.json", self.path):
            self.send_error(404)
            return
        status = 304 if not_modified(self.headers) else 200
        origin_id = uuid.uuid4().hex
        # One JSON line per request; never log credentials/cookies or arbitrary headers.
        print(json.dumps({
            "time": time.time(), "origin_id": origin_id, "path": self.path,
            "headers": {h: self.headers.get_all(h) for h in HEADERS_TO_LOG},
            "status": status, "etag": ETAG,
            "body_bytes": 0 if status == 304 else len(BODY),
        }), flush=True)
        self.send_response(status)
        self.send_header("ETag", ETAG)
        self.send_header("Last-Modified", LAST_MODIFIED)
        self.send_header("Cache-Control", "public, max-age=120")
        self.send_header("X-Lab-Origin-Id", origin_id)
        self.send_header("Content-Type", "application/json")
        if status == 200:
            self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        if status == 200:
            self.wfile.write(BODY)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Origin).serve_forever()


if __name__ == "__main__":
    main()

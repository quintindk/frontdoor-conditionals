"""Collect observations from an explicitly supplied LAB origin and LAB edge."""
import argparse
from hashlib import sha256
import gzip
import io
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener, Request
import uuid


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def lab_base_url(value):
    url = urlsplit(value)
    if (url.scheme not in ("http", "https") or not url.hostname
            or url.username is not None or url.password is not None
            or "?" in value or "#" in value or url.path not in ("", "/")):
        raise ValueError("Use an HTTP(S) base URL without credentials, path or query")
    if url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Non-local endpoints must use HTTPS")
    url.port  # Validate the port before any network request.
    return value.rstrip("/")


def fetch(base, path, headers):
    request_id = uuid.uuid4().hex
    sent = {"Accept-Encoding": "identity", "X-Lab-Request-Id": request_id, **headers}
    started = time.monotonic()
    # No implicit proxy, redirects, retries, cookies or credentials. Hash raw bytes.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(Request(base + path, headers=sent), timeout=30)
    except HTTPError as error:
        response = error  # 304 is evidence, not a failed test runner.
    with response:
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("Unexpected response over 1 MiB; not this lab fixture")
        record = {
            "request_id": request_id, "time": time.time(), "path": path,
            "sent_headers": sent, "status": response.status,
            "headers": dict(response.headers.items()),
            "body_bytes": len(body), "body_sha256": sha256(body).hexdigest(),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }
        if response.status == 200 and response.headers.get("Content-Encoding", "").lower() == "gzip":
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as compressed:
                decoded = compressed.read(1024 * 1024 + 1)
            if len(decoded) > 1024 * 1024:
                raise ValueError("Decoded response exceeds 1 MiB")
            record["decoded_body_bytes"] = len(decoded)
            record["decoded_body_sha256"] = sha256(decoded).hexdigest()
        return record


def header(response, name):
    return next((v for k, v in response["headers"].items() if k.lower() == name.lower()), None)


def run(origin, edge, encoding="identity", label="unspecified", warm_attempts=6, run_id=None):
    run_id = run_id or uuid.uuid4().hex
    print(json.dumps({"run": run_id, "configuration_label": label,
                      "origin": origin, "edge": edge, "encoding": encoding,
                      "notice": "Observations only; correlate origin logs. No automatic forwarding verdict."}), flush=True)
    for condition in ("etag", "weak", "nonmatch", "wildcard", "date", "precedence"):
        for state in ("cold", "warm"):
            # Separate fresh path for EACH cold case. Direct-origin GET does not warm AFD.
            path = f"/objects/{run_id}/{condition}-{state}/v1.json"
            baseline = fetch(origin, path, {"Accept-Encoding": "identity"})
            etag = header(baseline, "ETag")
            modified = header(baseline, "Last-Modified")
            if baseline["status"] != 200 or not etag or not modified:
                raise ValueError("Direct lab origin must supply 200, ETag and Last-Modified")
            conditions = {
                "etag": {"If-None-Match": etag},
                "weak": {"If-None-Match": "W/" + etag},
                "nonmatch": {"If-None-Match": '"deliberately-different"'},
                "wildcard": {"If-None-Match": "*"},
                "date": {"If-Modified-Since": modified},
                "precedence": {"If-None-Match": '"deliberately-different"', "If-Modified-Since": modified},
            }
            warmups = []
            warm_verified = False
            if state == "warm":
                for _ in range(warm_attempts):
                    warm = fetch(edge, path, {"Accept-Encoding": encoding})
                    warmups.append(warm)
                    if header(warm, "X-Cache") == "TCP_HIT":
                        warm_verified = True
                        break
                    time.sleep(1)
            observed = fetch(edge, path, {"Accept-Encoding": encoding, **conditions[condition]})
            print(json.dumps({
                "run": run_id, "case": condition, "requested_cache_state": state,
                "warm_verified_before_request": warm_verified,
                "baseline": baseline, "warmups": warmups, "conditional": observed,
                "interpretation": "Join by unique path and request ID to origin logs; a warm-up hit does not prove the next request hit the same cache.",
            }), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--edge", required=True)
    parser.add_argument("--encoding", choices=("identity", "gzip"), default="identity")
    parser.add_argument("--label", required=True, help="SKU, route configuration and compression state")
    parser.add_argument("--confirm-lab", action="store_true", help="Confirm both endpoints are approved test resources")
    args = parser.parse_args()
    if not args.confirm_lab:
        parser.error("Use --confirm-lab only for approved test endpoints")
    try:
        origin, edge = lab_base_url(args.origin), lab_base_url(args.edge)
    except ValueError as error:
        parser.error(str(error))
    run(origin, edge, args.encoding, args.label)


if __name__ == "__main__":
    main()

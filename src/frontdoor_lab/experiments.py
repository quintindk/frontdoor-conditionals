"""Additional approved-lab experiments. Records observations, not forwarding verdicts."""
import argparse
from datetime import datetime, timezone
import json
import time
import uuid

from .probe import fetch, header, lab_base_url, run


def emit(record):
    print(json.dumps(record), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("matrix", "ttl", "ttl-conditional", "canary", "edge-validator", "supplemental", "precedence-pair"))
    parser.add_argument("--origin", required=True)
    parser.add_argument("--edge", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--encoding", choices=("identity", "gzip"), default="identity")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--old-date", default="Thu, 01 Jan 1970 00:00:00 GMT")
    parser.add_argument("--wait-seconds", type=int, default=60, help="Bounded canary propagation wait")
    parser.add_argument("--confirm-lab", action="store_true", required=True)
    parser.add_argument("--expect", choices=("cache", "no-cache", "gzip", "uncompressed"), default="cache")
    args = parser.parse_args()
    try:
        args.origin, args.edge = lab_base_url(args.origin), lab_base_url(args.edge)
    except ValueError as error:
        parser.error(str(error))
    if args.repeats < 1 or args.wait_seconds < 1:
        parser.error("Repeats and wait-seconds must be positive")
    for repeat in range(args.repeats):
        run_id = uuid.uuid4().hex
        label = f"{args.label}; repeat {repeat + 1}"
        if args.mode == "matrix":
            run(args.origin, args.edge, args.encoding, label, run_id=run_id)
            continue
        if args.mode == "supplemental":
            for case in ("old-date", "etag-old-date", "etag-list"):
                for state in ("cold", "warm"):
                    path = f"/objects/{run_id}/{case}-{state}/v1.json"
                    baseline = fetch(args.origin, path, {})
                    etag = header(baseline, "ETag")
                    if baseline["status"] != 200 or not etag:
                        raise RuntimeError("Direct origin baseline must return 200 and an ETag")
                    conditions = {
                        "old-date": {"If-Modified-Since": args.old_date},
                        "etag-old-date": {"If-None-Match": etag, "If-Modified-Since": args.old_date},
                        "etag-list": {"If-None-Match": f'"different", W/{etag}'},
                    }[case]
                    direct = fetch(args.origin, path, conditions)
                    warmups = []
                    if state == "warm":
                        for attempt in range(6):
                            warmups.append(fetch(args.edge, path, {"Accept-Encoding": args.encoding}))
                            if header(warmups[-1], "X-Cache") == "TCP_HIT":
                                break
                            time.sleep(1)
                    observed = fetch(args.edge, path, {"Accept-Encoding": args.encoding, **conditions})
                    emit({"run": run_id, "case": case, "requested_cache_state": state,
                          "label": label, "baseline": baseline, "direct_control": direct,
                          "warmups": warmups, "conditional": observed,
                          "warm_verified_before_request": bool(warmups and header(warmups[-1], "X-Cache") == "TCP_HIT"),
                          "expected_status": 200 if case == "old-date" else 304})
            continue
        path = f"/objects/{run_id}/{args.mode}/v1.json"
        emit({"run": run_id, "kind": args.mode, "label": label, "path": path,
              "started": datetime.now(timezone.utc).isoformat()})
        baseline = fetch(args.origin, path, {})
        emit({"phase": "baseline", **baseline})
        if baseline["status"] != 200 or not header(baseline, "ETag") or not header(baseline, "Last-Modified"):
            raise RuntimeError("Direct origin baseline must return 200 and both validators")
        headers = {"Accept-Encoding": args.encoding}
        warm = None
        attempts = max(1, args.wait_seconds // 15) if args.mode == "canary" else 10
        for attempt in range(attempts):
            warm = fetch(args.edge, path, headers)
            emit({"phase": "warmup", **warm})
            if args.mode in ("canary", "precedence-pair") and args.expect == "no-cache":
                if header(warm, "X-Cache") == "CONFIG_NOCACHE" and warm["status"] == 200:
                    break
            elif warm["status"] == 200 and header(warm, "X-Cache") == "TCP_HIT":
                if args.mode == "canary" and args.expect == "uncompressed":
                    if header(warm, "Content-Encoding") is None and warm["body_sha256"] == baseline["body_sha256"]:
                        break
                elif args.mode != "canary" or args.expect != "gzip" or header(warm, "Content-Encoding") == "gzip":
                    break
            time.sleep(15 if args.mode == "canary" else 1)
        else:
            raise RuntimeError("Expected data-plane canary/cache-hit state not observed")
        if args.mode == "canary":
            continue
        if args.mode == "precedence-pair":
            etag = header(baseline, "ETag")
            for phase, conditions in (
                ("etag-only-before", {"If-None-Match": etag}),
                ("etag-with-old-date", {"If-None-Match": etag, "If-Modified-Since": args.old_date}),
                ("etag-only-after", {"If-None-Match": etag}),
                ("both-matching", {"If-None-Match": etag, "If-Modified-Since": header(baseline, "Last-Modified")}),
            ):
                emit({"phase": phase, **fetch(args.edge, path, {**headers, **conditions})})
            continue
        if args.mode == "edge-validator":
            if args.encoding == "gzip":
                if header(warm, "Content-Encoding") != "gzip" or warm.get("decoded_body_sha256") != baseline["body_sha256"]:
                    raise RuntimeError("Compressed representation not verified")
            etag = header(warm, "ETag")
            if etag is None:
                emit({"phase": "edge-validator-unavailable", "path": path})
            else:
                emit({"phase": "conditional-edge-etag", **fetch(args.edge, path, {**headers, "If-None-Match": etag})})
            emit({"phase": "identity-after-gzip", **fetch(args.edge, path, {"Accept-Encoding": "identity"})})
            emit({"phase": "gzip-after-identity", **fetch(args.edge, path, {"Accept-Encoding": "gzip"})})
            continue
        # Wait past the fixture TTL from the last verified hit, not from initial fill.
        emit({"phase": "ttl-wait", "seconds": 130, "path": path})
        time.sleep(130)
        if args.mode == "ttl-conditional":
            emit({"phase": "after-ttl-conditional-first", **fetch(args.edge, path, {**headers, "If-None-Match": header(baseline, "ETag")})})
            continue
        emit({"phase": "after-ttl-unconditional", **fetch(args.edge, path, headers)})
        emit({"phase": "after-ttl-old-validator", **fetch(args.edge, path, {**headers, "If-None-Match": header(baseline, "ETag")})})


if __name__ == "__main__":
    main()

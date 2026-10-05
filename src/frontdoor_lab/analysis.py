"""Correlate recorded client requests with origin observations, without inferring log completeness."""
import argparse
from collections import Counter
import json
from pathlib import Path

from .probe import header


def decode_records(text):
    # Concurrent fixture prints can share one ingested line. Preserve every JSON object.
    records = []
    decoder = json.JSONDecoder()
    remaining = text.lstrip()
    while remaining:
        record, end = decoder.raw_decode(remaining)
        records.append(record)
        remaining = remaining[end:].lstrip()
    return records


def load_logs(raw):
    tables = raw["Tables"]
    status = next(table for table in tables if "StatusCode" in [c["ColumnName"] for c in table["Columns"]])
    names = [column["ColumnName"] for column in status["Columns"]]
    if any(row[names.index("StatusCode")] != 0 for row in status["Rows"]):
        raise ValueError("Log query did not complete cleanly")
    table = tables[0]
    names = [column["ColumnName"] for column in table["Columns"]]
    unique = {}
    for row in table["Rows"]:
        for record in decode_records(row[names.index("Log_s")]):
            if record["origin_id"] in unique and unique[record["origin_id"]] != record:
                raise ValueError("Conflicting origin records")
            unique[record["origin_id"]] = record
    return list(unique.values())


def correlate(case, logs):
    response = case["conditional"]

    def matches(request):
        return [log for log in logs if log["path"] == request["path"]
                and request["request_id"] in (log["headers"].get("X-Lab-Request-Id") or [])]

    origins = matches(response)
    expected = case.get("expected_status", 200 if case["case"] in ("nonmatch", "precedence") else 304)
    body_ok = response["body_bytes"] == 0 if response["status"] == 304 else (
        response.get("decoded_body_sha256", response["body_sha256"]) == case["baseline"]["body_sha256"])
    return {
        "run": case["run"], "case": case["case"], "state": case["requested_cache_state"],
        "path": response["path"], "request_id": response["request_id"],
        "status": response["status"], "cache": header(response, "X-Cache"),
        "content_encoding": header(response, "Content-Encoding"), "bytes": response["body_bytes"],
        "etag": header(response, "ETag"), "sent_headers": response["sent_headers"],
        "warm_verified": case["warm_verified_before_request"],
        "status_matches_fixture_condition": response["status"] == expected,
        "body_valid": body_ok, "baseline_origin_records": len(matches(case["baseline"])),
        "origin_records": [{"origin_id": row["origin_id"], "status": row["status"],
                            "headers": row["headers"]} for row in origins],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", required=True)
    parser.add_argument("clients", nargs="+")
    args = parser.parse_args()
    logs = load_logs(json.loads(Path(args.logs).read_text()))
    rows = []
    for filename in args.clients:
        for line in Path(filename).read_text().splitlines():
            case = json.loads(line)
            if "case" in case:
                rows.append({"source": filename, **correlate(case, logs)})
    counts = Counter((row["source"], row["state"], row["status"], row["cache"],
                      len(row["origin_records"])) for row in rows)
    print(json.dumps({
        "notice": "Absent matches are observations, not proof of lossless logging or a particular cache tier.",
        "cases": len(rows), "origin_records": len(logs),
        "missing_baselines": sum(row["baseline_origin_records"] == 0 for row in rows),
        "status_mismatches": sum(not row["status_matches_fixture_condition"] for row in rows),
        "invalid_bodies": sum(not row["body_valid"] for row in rows),
        "groups": [{"source": key[0], "state": key[1], "status": key[2], "cache": key[3],
                    "matched_origin_count": key[4], "count": count} for key, count in counts.items()],
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()

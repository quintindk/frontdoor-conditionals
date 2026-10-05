# Methodology and Evidence

## Questions

1. Does the edge evaluate a client's validator against a cached representation?
2. On a miss, does the origin receive the client's conditional header?
3. What does the intermediary do with the origin response, including 304s and subsequent fetches?

A client-side status code cannot answer all three. Capture the complete request/response sequence and correlate it with origin observations.

## Fixture

The origin serves a fixed 8,029-byte JSON representation with a SHA-256-based strong ETag, a fixed Last-Modified timestamp and a 120-second TTL. Conditional GET supports weak/list/wildcard ETag comparison and ETag precedence over dates. This is a bounded fixture, not a general-purpose RFC implementation.

Only `/health` and `/objects/<run>/<case>/v1.json` are served. There is no write API or filesystem access. Range is logged but deliberately ignored: the origin returns the complete representation rather than implementing partial responses. This limits transfer of conclusions to native range-serving origins.

Logs describe the status/body length the handler intends to send before the response is written. They are not a packet capture or proof that an intermediary consumed every byte.

## Cold and Warm Paths

For each cold condition, generate a new path and obtain its validators **directly from the origin**. The first edge request to that path must be conditional. Obtaining validators from the edge first would warm the supposedly cold case.

For warm paths, record preparatory GETs until `X-Cache: TCP_HIT`, then issue the conditional request. Classify that request using its own response headers and origin logs. It may reach a different cache tier or require revalidation. If warming fails, preserve the observations but do not claim a verified hit.

Use fixed endpoints for baseline, no-cache and compression controls. Export their actual configuration and validate the data plane before each run. Exclude transitional results rather than labelling old/new mixed behaviour as a stable control.

## Cases

The base matrix covers matching strong and weak ETags, non-match, wildcard, matching date and non-matching ETag plus matching date. Supplemental tests add older dates, ETag lists and matching ETag plus older date. The latter is necessary to test both directions of precedence.

`precedence-pair` uses one path for matching ETag alone, the same tag with an older date, ETag alone again, and both matching headers. Separate `ttl` and `ttl-conditional` paths distinguish unconditional-first and conditional-first requests after expiry. Do not call a second request after revalidation an independent stale-entry test.

For compression, confirm `Content-Encoding` on a full 200 and compare decoded content hashes. Raw encoded hashes and lengths remain separate. A changed or missing edge validator is not, by itself, proof that conditional requests are unsupported. `If-None-Match` uses weak comparison, so 304 does not prove byte equality across encoded representations.

## Correlation

Join by unique path and `X-Lab-Request-Id`. A cached `X-Lab-Origin-Id` identifies the original fill, not a new origin request. Retain all records for the path to detect retries, request collapsing and secondary fetches.

| Trace | Bounded interpretation |
|---|---|
| Exact client validator in an origin record | It reached that origin on that request |
| Correlated origin request without the validator | It was absent at the instrumented origin on that attempt |
| Origin 200, client 304 | The intermediary processed the client condition separately from the origin request |
| Hit response, no origin match in collected logs | Supports cache-tier handling, subject to log completeness |
| Missing record with incomplete/delayed logs | Inconclusive |

Collect all revisions/replicas, query status metadata, ingestion boundaries and sentinel requests. Check that known direct requests are present. A successful query and end sentinel strengthen coverage but do not guarantee lossless logging. Never silently discard malformed records or partial query results.

## Scope and Privacy

Local tests prove harness behaviour only. A cloud run establishes observations for its recorded configuration, not an implementation rationale, roadmap, contract or universal behaviour across SKUs and locations.

Raw outputs include endpoint URLs, correlation headers, resource identifiers and filenames. Keep them under ignored `evidence/`, review before sharing, and never include credentials in probe headers or URLs. Publishing aggregate findings does not make the underlying deployment details public.

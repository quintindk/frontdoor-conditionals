# Front Door Conditional-Request Lab

A small, dependency-free Python harness for observing conditional GET requests through Azure Front Door. It distinguishes **what the client receives**, **what reaches the origin**, and **what the cache handles**.

It is a synthetic test fixture, not a production HTTP server, an Azure emulator or official Microsoft guidance.

```text
Probe --------------------------> instrumented origin (direct control)
  |
  +--> Azure Front Door --------> same origin
```

## Findings

A study on **5 October 2026** used Azure Front Door Standard and a synthetic Container Apps origin in South Africa North. It recorded **216 conditional observations** across cache/compression settings, cold and warmed paths, and three repeats.

| Observation | Result in this setup |
|---|---|
| Ordinary matching ETag or date | Client received `304`, including cold requests |
| Cold, cache-enabled request | Client validators were absent at the origin, although the edge still returned `304` when appropriate |
| Warm cache hit | Conditional responses had no corresponding origin access in the collected logs |
| Caching disabled | Client validators reached the origin unchanged |
| Gzip | Correct decoded content, weakened ETag, working ordinary `304` responses |
| TTL expiry | Front Door used origin validators to revalidate cached content |
| Matching ETag **plus an older date** | **Cached response was `200` instead of the expected `304`, in 18 of 18 targeted cases** |

The accepted matrix contained **198 expected outcomes and 18 occurrences of that same paired-header discrepancy**. Same-path checks reproduced `304` with ETag alone, `200` after adding an older date, and `304` after removing the date. [RFC 9110 section 13.1.3](https://httpwg.org/specs/rfc9110.html#field.if-modified-since) requires recipients to ignore `If-Modified-Since` when `If-None-Match` is present.

**Bounded workaround:** send `If-None-Match` alone, using the validator for the selected representation. These findings do not support a blanket claim that Front Door ignores ETags. They are observations, not a service-team-confirmed diagnosis or a support guarantee.

Read the [full findings and limitations](docs/findings-2026-10-05.md). Native Blob, mutable-content freshness, other SKUs and other geographies were **not validated**. Raw deployment-specific evidence is not published.

## Quick Start

Python 3.11 or newer is required. The runtime uses only the standard library.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -B -m unittest discover -s tests -p 'test_*.py' -v
frontdoor-origin
```

The origin listens on `127.0.0.1:8080` by default. In another terminal with the same environment activated:

```bash
frontdoor-probe \
  --origin http://127.0.0.1:8080 \
  --edge http://127.0.0.1:8080 \
  --label 'loopback, no CDN' --confirm-lab
```

Loopback validates the harness only. It cannot demonstrate cache behaviour, and its warm-up checks will not find a CDN hit.

Without installing the package, run the tests with:

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

## Run Against Your Lab

Deploy only to resources you own or are authorised to test. Set `LAB_ORIGIN` and `LAB_EDGE` to your HTTPS base URLs, without credentials, paths or query strings. The [infrastructure runbook](infra/README.md) describes an optional Container Apps and Front Door deployment.

```bash
umask 077
mkdir -p evidence
frontdoor-probe \
  --origin "$LAB_ORIGIN" --edge "$LAB_EDGE" \
  --label 'Standard; cache on; compression off; identity' \
  --confirm-lab > evidence/baseline.jsonl

frontdoor-experiments precedence-pair \
  --origin "$LAB_ORIGIN" --edge "$LAB_EDGE" \
  --old-date 'Tue, 01 Oct 2024 00:00:00 GMT' \
  --label 'Paired-validator reproduction' \
  --repeats 3 --confirm-lab > evidence/precedence.jsonl
```

Choose an older date than your origin's `Last-Modified`. The bundled fixture has a fixed timestamp. Additional experiment modes cover repeated matrices, supplemental date/list conditions, gzip validators, representation selection and independent TTL checks. Use `frontdoor-experiments --help` for options.

The commands collect observations rather than declaring CDN success. A warm-up hit does not prove the next request uses the same cache. Read the [methodology](docs/methodology.md) before interpreting results.

## Project Layout

```text
src/frontdoor_lab/   Synthetic origin, probes, experiments and correlation
tests/              Local-only unit and loopback tests
infra/              Parameterised Bicep and deployment runbook
docs/               Methodology and sanitised findings
evidence/           Your generated evidence, ignored by Git
```

The origin serves approximately 8 KB of JSON with a deterministic strong ETag, fixed Last-Modified and 120-second TTL. It supports a bounded subset of conditional GET behaviour, has no write API, and intentionally ignores Range requests. Its access logs use a header allow-list and do not record Authorization or Cookie.

## Container

```bash
docker build --platform linux/amd64 -t frontdoor-conditionals:local .
docker run --rm -p 127.0.0.1:8080:8080 frontdoor-conditionals:local
```

Use `linux/arm64` instead for native local execution on an ARM host. The build context contains only the origin package files and Dockerfile, not evidence or deployment parameters.

## Safety and Privacy

- Azure resources incur charges, including Front Door's base charge and managed networking. There is no automatic teardown.
- Always specify the intended subscription explicitly. Do not bypass deployment policies to make a control work.
- Raw logs and probe output can contain hostnames, request IDs, profile headers and local filenames. Ignored files are **not automatically safe to publish**.
- Keep credentials, actual parameter files, raw evidence and private operational notes outside published history and releases.
- Do not use this development server for production traffic or private data.

## Licence

[MIT](LICENSE). Linked standards and vendor documentation retain their respective licences.

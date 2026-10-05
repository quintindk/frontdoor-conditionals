# Contributor Instructions

- Read `README.md`, `docs/methodology.md` and the dated findings before changing experiments.
- Run `PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_*.py' -v`.
- Keep the harness dependency-free at runtime. Use synthetic data and approved lab endpoints only.
- Never deploy into an implicit Azure subscription. Provisioning and billable tests require explicit approval of scope and spending.
- Never commit credentials, populated deployment parameters, live resource identifiers, raw evidence or private operational notes.
- Keep raw observations under ignored `evidence/`. Review generated output separately before sharing it.
- Preserve unique cold-case paths and obtain their initial validators directly from the origin.
- Correlate requests with origin logs. A status code alone proves neither forwarding nor stripping.
- Keep measured behaviour, HTTP requirements and vendor support statements distinct. Local tests validate the harness, not the CDN.
- Do not deploy, delete resources, change policy, publish additional branches or send external messages without explicit approval.

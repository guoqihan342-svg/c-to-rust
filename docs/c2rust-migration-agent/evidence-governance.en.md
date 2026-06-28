# Evidence Governance

This file documents the current evidence portability, cost, and retention entrypoint. The Chinese primary document is `evidence-governance.md`.

## Goal

`validation/tools/evidence_governance.py` is a non-destructive report tool that answers two questions:

- Whether new milestone evidence uses local absolute paths, old WSL/Windows work directories, or temporary directories as cross-machine claim anchors.
- How many evidence artifacts exist, how many bytes they consume, which runtime records are present, and which artifacts belong to release, CI smoke, diagnostic-only, or historical archive classes.

The report surfaces problems, but it does not delete, compress, or rewrite historical evidence. Historical issues may remain as audit records; new milestone evidence should prefer repo-relative paths, profile ids/hashes, and artifact hashes.

## Commands

```bash
python validation/tools/evidence_governance.py
```

Write the report to a file:

```bash
python validation/tools/evidence_governance.py --output validation/evidence-governance-report.json
```

Unit tests:

```bash
python -B -m unittest validation.tools.test_evidence_governance
```

## Portability Rules

Hard issues:

- Claim-anchor areas such as `evidence`, `source_artifacts`, `artifact_refs`, `generated_artifacts`, `dependent_artifacts`, `accepted_paths`, or `paths` contain absolute or temporary paths such as `C:\...`, `F:\...`, `/mnt/c/...`, or `/tmp/...`.
- `translator.artifact_paths` or `source_boundary.files` contains local absolute paths.
- `competition_environment` / `competition_environment_identity` is missing `sha256`.

Diagnostic metadata:

- `clang_path`
- `metadata.source_root`
- `lowering_report.arguments`
- `source_file`
- skipped C2Rust baseline `reference_tree`
- stdout/stderr/log excerpts

These fields may record host facts, but they must not become reproducible entrypoints for release claims.

## Retention Classes

- `committed_release`: evidence required by external milestones or named-slice claims; artifact hashes must be retained.
- `ci_smoke`: short-lived CI smoke evidence that can be regenerated.
- `diagnostic_only`: debug logs, stdout/stderr, and host-local diagnostics; not semantic claim anchors.
- `historical_archive`: older L1/L2 catalogues, experiments, and broad audit material for historical traceability only.

`target/full-regression/<run-id>` is `ci_smoke`, not committed release evidence. Its `summary.json`, `events.jsonl`, and logs are reusable developer/CI smoke records; local absolute `evidence_root`, `working_directory`, and `log` fields are treated as diagnostic metadata rather than claim anchors. Each pipeline report lists `artifact_count`, `total_bytes`, `runtime_ms`, `retention_class`, compression/prune policy, and `report_artifacts`.

## Current Boundary

The tool is the report/validator foundation, not a cleanup tool. It exposes historical absolute paths but does not require the whole repository to pass a portability gate immediately. Promoting it to a release gate requires historical evidence classification, retention-policy confirmation, and refreshed milestone evidence first.

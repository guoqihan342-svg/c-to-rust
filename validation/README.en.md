# English Mirror: Validation README

Chinese original: `README.md`.

This file is the English mirror for `validation/README.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the validation framework documentation and reviewer-facing gates. It is intentionally concise for older plans, templates, and Superpowers records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# Multi-Project C-to-Rust Validation`
- `## Files`
- `## Fast Commands`
- `## Competition Environment Profile`
- `## Real Source Slice Extraction`
- `## C2Rust Baseline, Route, And Validation Profile`
- `## Current Candidate Count`
- `## Wave2 Boundary`
- `## Full L1 Attempt Boundary`
- `## L1 Failure Classification`
- `## L1 Low-Cost Remediation`
- `## Non-Equivalence Boundary`

## Maintenance Notes

- Keep filenames paired as `README.md` and `README.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `README.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, Superpowers tasks, and validation checklists are scoped artifacts only.
- Current public packet contracts require `summary.workflow_metrics`, `quantitative_evaluation`, top-level `progress_delta_ledger`, and `summary.progress_delta_ledger` to match the bound `judge-milestone-bundle.json`, with top-level `semantic_gate=false`, `generated_draft_semantic_pass=false`, and `translation_coverage_numerator=0`. Scorecard outcome counts may still expose route-governance-validated `translator_generated_semantic_pass_count`. `progress_delta_ledger.workflow_delta` may fill repair/auto-recovery/rollback review counts from verified `before_after_repair_exhibit` evidence by entrypoint when workflow repair activity is sparse; this does not rewrite `summary.workflow_metrics`.
- Current judge-entrypoint validation checks non-null `context_pack.entrypoints` values as repo-relative POSIX paths and cross-checks workers across the resume manifest, context pack, and agent index.

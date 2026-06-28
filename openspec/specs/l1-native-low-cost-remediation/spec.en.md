# English Mirror: L1 Native Low Cost Remediation OpenSpec Spec

Chinese original: `spec.md`.

This file is the English mirror for `openspec/specs/l1-native-low-cost-remediation/spec.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers a formal OpenSpec capability specification. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `## Purpose`
- `## Requirements`
- `### Requirement: Remediation candidates are bounded`
- `#### Scenario: Candidate selection excludes host dependency failures`
- `### Requirement: Catalog recipe changes are minimal and auditable`
- `#### Scenario: Recipe change preserves validation scope`
- `### Requirement: Remediated projects are rerun`
- `#### Scenario: Rerun evidence is generated`
- `### Requirement: Global L1 summary reflects latest accepted evidence`
- `#### Scenario: Summary separates passed and failed projects`
- `### Requirement: Remediation report avoids overclaiming`
- `#### Scenario: Report states validation boundary`

## Maintenance Notes

- Keep filenames paired as `spec.md` and `spec.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `spec.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

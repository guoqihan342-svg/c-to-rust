# English Mirror: Full Regression Runner

Chinese original: `full-regression-runner.md`.

This file is the English mirror for `docs/c2rust-migration-agent/full-regression-runner.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the migration-agent design, roadmap, evidence, and architecture documentation set. It is intentionally concise for older plans, templates, and Superpowers records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# Full Regression Runner`
- `## Recommended Local Gate`
- `## Repeated Full Rounds`
- `## Evidence Files`
- `## Claim Boundaries`

## Maintenance Notes

- Keep filenames paired as `full-regression-runner.md` and `full-regression-runner.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `full-regression-runner.en.md` with the repository-standard mirror notice.
- Routine full regression uses 1,000 FlashDB stress iterations; 10,000 is not a normal acceptance requirement.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, Superpowers tasks, and validation checklists are scoped artifacts only.

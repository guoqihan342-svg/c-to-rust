# English Mirror: Gates

Chinese original: `gates.md`.

This file is the English mirror for `validation/gates.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the validation framework documentation and reviewer-facing gates. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# Validation Gates`
- `## L0: Catalog and Remote Probe`
- `## L1: Native C Build and Test Smoke`
- `## L2: Bounded Migration Slice`
- `## L3: Semantic and Performance Evidence`
- `## Full Regression Evidence Gates`
- `## Reporting Rules`

## Maintenance Notes

- Keep filenames paired as `gates.md` and `gates.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `gates.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

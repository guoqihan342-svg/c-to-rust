# English Mirror: L1 L2 Project Cards

Chinese original: `l1-l2-project-cards.md`.

This file is the English mirror for `validation/l1-l2-project-cards.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the validation framework documentation and reviewer-facing gates. It is intentionally concise for older plans, templates, and Superpowers records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# L1/L2 Project Cards`
- `## Execution Rules`
- `## Priority Order`
- `## First Wave Detailed Cards`
- `### SQLite`
- `### zstd`
- `### libuv`
- `### libevent`
- `### Lua`
- `### zlib-ng`
- `## Second Wave Detailed Cards`
- `### Valkey / Redis`
- `### curl`
- `### Git`
- `### nginx`
- `### libpng`

## Maintenance Notes

- Keep filenames paired as `l1-l2-project-cards.md` and `l1-l2-project-cards.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `l1-l2-project-cards.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, Superpowers tasks, and validation checklists are scoped artifacts only.

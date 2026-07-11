# English Mirror: Flashdb Rust README

Chinese original: `README.md`.

This file is the English mirror for `flashDB_rust/README.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the FlashDB Rust skeleton documentation. It is intentionally concise for older plans, templates, and Superpowers records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

Current boundary note: `real-fdb-blob-make` has an independent L4 accepted-evidence semantic pass, but that does not make the generated draft itself semantic pass and does not generalize to the whole `flashDB_rust` skeleton or to `fdb_kv_set`.

## Source Outline

The Chinese source currently contains these major headings:

- `# flashDB_rust`
- `## Scope`
- `## Fast Verification`
- `## Optional Stress Diagnostics`
- `## Tool Fallbacks`
- `## CI Verification`
- `## Native Windows Verification`
- `## Fixture Replay and Diff`

## Maintenance Notes

- Keep filenames paired as `README.md` and `README.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `README.en.md` with the repository-standard mirror notice.
- Routine local verification and CI do not run loop stress; the stress command is a separately approved manual diagnostic only.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, Superpowers tasks, and validation checklists are scoped artifacts only.

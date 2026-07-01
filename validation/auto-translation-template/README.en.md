# English Mirror: Auto Translation Template README

Chinese original: `README.md`.

This file is the English mirror for `validation/auto-translation-template/README.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers a reusable validation template or checklist. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# Auto Translation Evidence Template`
- `## Evidence Files`
- `## Alias Gate Summary`
- `## Rules`

## Maintenance Notes

- Keep filenames paired as `README.md` and `README.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `README.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.
- Generated C2Rust baseline manifests must include `compile` evidence bound to the same output path/status/sha256. The compile check is compile-only candidate evidence, not semantic acceptance.

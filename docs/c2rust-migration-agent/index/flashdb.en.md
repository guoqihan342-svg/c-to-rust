# English Mirror: Flashdb

Chinese original: `flashdb.md`.

This file is the English mirror for `docs/c2rust-migration-agent/index/flashdb.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the categorized document index for the migration-agent documentation set. It is intentionally concise for older plans, templates, and Superpowers records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- No Markdown headings are present in the Chinese source yet.

## Current FlashDB Evidence Summary

- Accepted evidence: `real-fdb-calc-crc32`, `real-fdb-blob-make`, `real-fdb-kv-del`, and `real-fdb-kv-set`. `real-fdb-kv-set` is an exact typed-IR generated draft acceptance for the uninitialized-DB `return_code=FDB_INIT_FAILED` fixture.
- Open semantics: initialized `fdb_kv_set`/delete paths, blob persistence, `fdb_kv_set_blob`, and complete external-callee semantics remain open.

## Maintenance Notes

- Keep filenames paired as `flashdb.md` and `flashdb.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `flashdb.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, Superpowers tasks, and validation checklists are scoped artifacts only.

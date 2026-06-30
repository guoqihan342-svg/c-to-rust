# English Mirror: Build And C2Rust Baseline

Chinese original: `build-and-c2rust-baseline.md`.

This file is the English mirror for `docs/c2rust-migration-agent/build-and-c2rust-baseline.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the migration-agent design, roadmap, evidence, and architecture documentation set. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# Build Capture and C2Rust Baseline`
- `## FlashDB Source`
- `## Feature Matrix for First Run`
- `## Expected `compile_commands.json` Workflow`
- `## C2Rust Baseline Command`
- `## Current Host Constraint`
- `## C Oracle Fallback`

Current operational note: `auto_migrate.py` keeps C2Rust generation disabled by default. In an environment with C2Rust installed, set `C2RUST_BASELINE_GENERATION=1` and provide `build_profile.compiler_command_source` pointing at `compile_commands.json`; generated output is recorded as path/status/sha256 plus compile-only `rustc --crate-type lib` status, and remains `candidate_context_only`. Compile success is not semantic acceptance.

## Maintenance Notes

- Keep filenames paired as `build-and-c2rust-baseline.md` and `build-and-c2rust-baseline.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `build-and-c2rust-baseline.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

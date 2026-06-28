# English Mirror: Bounded Auto Translation Pipeline OpenSpec Spec

Chinese original: `spec.md`.

This file is the English mirror for `openspec/specs/bounded-auto-translation-pipeline/spec.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers a formal OpenSpec capability specification. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# bounded-auto-translation-pipeline Specification`
- `## Purpose`
- `## Requirements`
- `### Requirement: Machine-Generated Slice Spec And Build Profile Input`
- `#### Scenario: L1-passed slice is accepted`
- `#### Scenario: Real source extraction precedes translation`
- `#### Scenario: Slice spec remains the downstream contract`
- `#### Scenario: Missing L1 evidence blocks translation`
- `#### Scenario: Build profile records semantic inputs`
- `#### Scenario: Platform-dependent slices declare their boundary`
- `#### Scenario: Syntax index cannot replace semantic evidence`
- `### Requirement: Real C Frontend Before Scale Claims`
- `#### Scenario: Corrode-style frontend lesson is adopted`
- `#### Scenario: L1 target count is not translation evidence`
- `### Requirement: Context Type CFG And Pointer Evidence`
- `#### Scenario: Context artifacts are emitted before code generation`

## Maintenance Notes

- Keep filenames paired as `spec.md` and `spec.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `spec.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

# English Mirror: Flashdb L3 Agent Migration Loop OpenSpec Spec

Chinese original: `spec.md`.

This file is the English mirror for `openspec/specs/flashdb-l3-agent-migration-loop/spec.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers a formal OpenSpec capability specification. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `## Purpose`
- `## Requirements`
- `### Requirement: Bounded L3 Slice Selection`
- `#### Scenario: KVDB lifecycle slice is declared`
- `#### Scenario: Cross-file context is captured before patching`
- `### Requirement: C Oracle And Rust Replay Diff`
- `#### Scenario: Reports use the same fixture`
- `#### Scenario: Behavior fields cannot be accepted differences`
- `#### Scenario: Layout metadata can be explicitly accepted`
- `### Requirement: Compile Self-Healing Loop`
- `#### Scenario: Rust compiler errors are classified`
- `#### Scenario: PatchPlan is generated before automatic repair`
- `#### Scenario: Unsafe or semantic contract changes stop automation`
- `### Requirement: Verification Escalation And Evidence`
- `#### Scenario: Validation reruns are staged`
- `#### Scenario: L3 evidence files are written`

## Maintenance Notes

- Keep filenames paired as `spec.md` and `spec.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `spec.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

# English Mirror: Handoff Context

Chinese original: `CONTEXT.md`.

This file is the English mirror for `CONTEXT.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the short handoff context for continuing Codex or Agent sessions. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `## 当前工作区`
- `## 文档入口`
- `## 待办规则`
- `## 当前能力边界`
- `## 常用验证命令`
- `## 最近交接`

## Current Handoff Summary

- Current branch: `codex/agent-harness-flashdb-mvp`.
- `real-fdb-calc-crc32` and `real-fdb-blob-make` currently pass through L4 accepted-evidence-authoritative semantic bindings; generated Rust drafts remain candidates with `generated_draft_semantic_pass=false`.
- `fdb_kv_set` remains L4 refused/blocked until external callee shim/model/oracle semantics are closed.
- The OpenCode harness has a minimal `run-worker` executor for deterministic runs and an OpenCode wrapper mode; SQLite remains a scheduling ledger, not evidence.

## Maintenance Notes

- Keep filenames paired as `CONTEXT.md` and `CONTEXT.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `CONTEXT.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

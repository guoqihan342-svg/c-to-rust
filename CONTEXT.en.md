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

- Current branch: `codex/flashdb-rust-skeleton`.
- `real-fdb-calc-crc32` and `real-fdb-blob-make` currently pass through L4 accepted-evidence-authoritative semantic bindings; generated Rust drafts remain candidates with `generated_draft_semantic_pass=false`.
- The real `real-fdb-calc-crc32` C2Rust baseline now generates and passes compile-only validation. Direct replay evidence is refreshed as `status=passed` / `observable_replay_pass=true` / `semantic_pass=false`, while the `verified unsafe baseline` is still correctly blocked on `c2rust_bound_gate_refs_not_implemented`; next is binding C oracle, Rust replay, diff, negative diff, unsafe, and final verification to the same C2Rust output.
- `fdb_kv_set` remains L4 refused/blocked until external callee shim/model/oracle semantics are closed.
- The OpenCode harness has a minimal `run-worker` executor for deterministic runs and an OpenCode wrapper mode; SQLite remains a scheduling ledger, not evidence.

## Maintenance Notes

- Keep filenames paired as `CONTEXT.md` and `CONTEXT.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `CONTEXT.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.
- 2026-07-02 handoff: the `opencode-agent-harness` stability review is directionally valid, but this branch has already absorbed timeout, atomic write, portable Python, retry cap, SQLite lock, fencing audit, `BEGIN IMMEDIATE`, and POSIX command-contract work into H7 regression gates. The active backlog stays focused on P0-C verified unsafe baseline and P0-D safety loop.
- `opencode.json` is a git-tracked file wired into the CI path filter and the `config/competition-env/bundle-manifest.json` archive contract; changes to it must be followed by a hash-binding resync.

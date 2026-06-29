# English Mirror:  README

Chinese original: `README.md`.

This file is the English mirror for `README.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the repository overview and quick entry point. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# C-to-Rust Progressive Migration Pipeline`
- `## 愿景`
- `## 架构概览`
- `## L0-L4 验证分层`
- `## 当前状态`
- `## 核心目录`
- `## 待办来源`
- `## OpenCode 比赛单次交互`
- `## 快速命令`
- `# 运行翻译器测试（默认 feature）`
- `# 运行翻译器测试（含 typed IR + clang frontend）`
- `# 运行 auto migration（以 FlashDB crc32 为例）`
- `# 验证自动翻译证据`
- `# 语义通过验证`
- `# 全量回归`
- `## 设计原则`

## Current OpenCode Competition Summary

The Chinese README now treats the 600-minute figure as an optional external evaluation budget, not as an optimization target. The competition path prioritizes accuracy and complete evidence, may process independent slices with parallel agents or batch workers, and requires isolated worker outputs plus common validator/final-verification acceptance.

The current typed-IR route includes local fixed-size integer arrays and readonly `static const` fixed-size integer global array index reads, including the restricted clang `array_filler` sparse initializer subset.

Current FlashDB accepted evidence includes both `real-fdb-calc-crc32` and `real-fdb-blob-make` through the L4 accepted-evidence-authoritative path. Their generated Rust drafts remain candidates with `generated_draft_semantic_pass=false`. `fdb_kv_set` still has L4 refused/blocked evidence because its external callee semantics are not closed by verified shims, models, or oracle evidence.

The current documentation-update branch is `codex/agent-harness-flashdb-mvp`; the baseline development branch remains `codex/flashdb-rust-skeleton`.

## Current Harness MVP Status

- Current branch: `codex/agent-harness-flashdb-mvp`.
- The OpenCode harness now has a minimal executor: `python -m validation.tools.opencode_agent_harness run-worker --mode deterministic` invokes the repo-local `scripts/c2rust-migrator.py --phase migrate --input ...` path and records the worker summary into the SQLite ledger when present.
- The OpenCode wrapper path is wired: `run-worker --mode opencode --opencode-variant max` runs the same assignment request. OpenCode/LLM output remains non-evidence.
- Accepted-evidence reuse is wired: `assign-slice --reuse-accepted-evidence --accepted-evidence-root validation/evidence --slice-spec <maintained-spec>` validates committed evidence inside an isolated worker output directory.
- FlashDB slices currently passing through semantic evidence binding: `real-fdb-calc-crc32` and `real-fdb-blob-make`. Both are L4 accepted-evidence authoritative; generated drafts are still not semantic pass.
- FlashDB slice currently blocked: `real-fdb-kv-set`. Its direct callees have signature/source provenance, but `strlen`, `fdb_blob_make`, `fdb_kv_set_blob`, and `fdb_kv_del` shim/model/oracle semantics are not closed.

Key commands mirrored from the Chinese README:

```bash
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-blob-make --slice-spec validation/slice-specs/flashdb-real-fdb-blob-make.json --require-semantic-pass
python -m validation.tools.opencode_agent_harness run-worker --db target/competition-out/state/opencode-agent-harness.sqlite3 --run-id run-demo-001 --worker-id worker-a --mode deterministic
```

## Maintenance Notes

- Keep filenames paired as `README.md` and `README.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `README.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

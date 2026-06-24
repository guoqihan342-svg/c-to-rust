## Why

`validation/evidence/flashdb/` now contains many replay reports, oracle reports, diff reports, summaries, logs, manifests, patch events, and error events. The current workflow can find them with ad hoc `rg`, but agents and reviewers lack a stable Rust-side command that returns traceable file, line, and snippet evidence in one machine-readable report.

`validation/evidence/flashdb/` 已经积累大量 replay、oracle、diff、summary、log、manifest、patch event 和 error event 文件。当前主要靠临时 `rg` 检索，缺少一个稳定的 Rust CLI，把命中文件、行号和摘要片段统一输出成可追溯 JSON。

## What Changes

- Add a small local-first `evidence-search` CLI command.
- Search `.json`, `.jsonl`, `.log`, and `.md` evidence files under a selected directory.
- Support keyword query through `--query <text>` and evidence root through `--evidence-dir <path>`.
- Emit JSON to stdout and optionally write the same JSON to `--report <path>`.
- Keep the implementation dependency-free, synchronous, deterministic, and unsafe-free.
- Do not add AI calls, background indexing, persistent cache files, or a new service in this slice.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add a local evidence trace search command for FlashDB L3 migration evidence.

## Impact

- `flashDB_rust/src/cli.rs`
- `flashDB_rust/tests/cli_smoke.rs`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive
- New evidence under `validation/evidence/flashdb/evidence-search-*`

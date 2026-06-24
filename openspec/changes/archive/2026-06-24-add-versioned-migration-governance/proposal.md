## Why

The migration agent already records many versions in baseline documents and per-slice evidence, but the L3 loop does not yet require a single version manifest that every future slice can validate before reusing caches, C oracle reports, or AI-generated patch candidates. Making version governance executable now prevents stale evidence from being treated as current when FlashDB source, Rust crate, toolchain, fixture schema, evidence schema, or agent contract versions drift.

迁移 Agent 已经在 baseline 文档和部分切片证据里记录了不少版本信息，但 L3 loop 还没有强制每个后续切片生成统一的 version manifest。现在把版本治理变成可执行门禁，可以避免 FlashDB 源码、Rust crate、工具链、fixture schema、evidence schema 或 Agent contract 漂移时继续复用过期缓存、C oracle 报告或 AI 候选补丁。

## What Changes

- Add a version manifest requirement to the existing FlashDB L3 migration loop.
- Add a small `flashdb-rust version-manifest` CLI command that emits a machine-readable manifest and can write it to `--report`.
- Require future L3 evidence to record agent contract version, context schema version, PatchPlan schema version, output crate version, FlashDB source commit, OpenSpec/rustc/cargo/git versions, fixture/evidence schema versions, Cargo.lock hash, and cache invalidation keys.
- Update the C2Rust migration agent docs to state that version manifests are a pre-edit and pre-cache-reuse gate.
- Keep version governance metadata-only: this change does not migrate additional FlashDB behavior, change public KVDB/TSDB semantics, introduce async/threading, or broaden accepted differences.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Require version-aware manifests and compatibility gates for every FlashDB L3 slice before cache reuse, compile self-healing, C/Rust diff claims, or archive.

## Impact

- `flashDB_rust/src/cli.rs` and CLI tests for the new `version-manifest` command.
- `docs/c2rust-migration-agent/agent-contract.md` and `docs/c2rust-migration-agent/baseline-and-versioning.md` for agent-facing version policy.
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive.
- New evidence under `validation/evidence/flashdb/version-governance-*`.
- No new dependencies, no unsafe code, and no change to existing replay/diff behavior.

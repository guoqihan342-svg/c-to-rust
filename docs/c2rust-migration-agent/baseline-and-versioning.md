英文镜像见 `baseline-and-versioning.en.md`。

# C2Rust Migration Agent Baseline and Versioning

中文说明：本文固定本次 `design-c2rust-migration-agent` 的版本基线，并规定后续 Agent、上下文 schema、PatchPlan 和 `flashDB_rust` 的升级策略。

English summary: this document pins the current migration baseline and defines versioning rules for the Agent contract, context store, PatchPlan, and output Rust crate.

## Locked Baseline

- OpenSpec: `1.4.1`
- Agent draft: `c2rust-migration-agent 0.1.0`
- Context schema: `0.1.0`
- PatchPlan schema: `0.1.0`
- Output crate: `flashDB_rust 0.1.0`
- Rust: `rustc 1.95.0`, `cargo 1.95.0`
- Git: `2.53.0.windows.3`
- FlashDB source: `https://gitcode.com/xwxf/FlashDB.git`
- FlashDB commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- C2Rust reference tree: `F:\agent\c2rust-master`
- C2Rust workspace package version: `0.22.1`
- C2Rust toolchain channel: `nightly-2022-11-03`

The machine-readable record is `baseline-record.json` in this directory.

## Version Bump Policy

### Agent SemVer

- Patch version: prompt wording, logging, documentation, or repair classifier tuning that does not change input/output fields.
- Minor version: new phase, optional field, new verification gate, new cache class, or backward-compatible schema extension.
- Major version: removed field, changed phase meaning, changed safety gate semantics, or incompatible runtime contract.

### Context Schema

- Patch version: index tuning or extra derived facts that do not change table/event meaning.
- Minor version: additive table, additive JSONL event field, or new fact category with default handling.
- Major version: renamed table, removed field, changed evidence meaning, or incompatible cache key rules.

### PatchPlan Contract

- Patch version: stricter validation, additional diagnostics, or risk label additions.
- Minor version: additive optional fields such as `forbidden_changes`, `verification_commands`, or `ai_prompt_hash`.
- Major version: changed required fields, changed rollback semantics, or changed acceptance gate rules.

### `flashDB_rust` Crate

- `0.1.x`: host-verifiable skeleton and first KVDB/TSDB subset.
- `0.2.x`: broader FlashDB semantics, stronger persistence fixtures, and feature-gated cache work.
- `1.0.0`: stable Rust-native API, verified public behavior, unsafe budget below 10%, and documented compatibility limits.

## Tool Version Rule

Every migration run must record exact tool versions before edits. If a tool is not available, record `NOT_FOUND`, the fallback behavior, and the impact on validation. Missing optional tools do not invalidate the design change, but they do block specific gates such as C2Rust generation, nextest, llvm-cov, fuzzing, or unsafe geiger reports until installed.

## Per-Slice Version Manifest Gate

Every FlashDB L3 slice MUST generate a version manifest before implementation edits and before cache reuse:

```bash
flashdb-rust version-manifest --report validation/evidence/flashdb/<slice>-version-manifest.json
```

The manifest is the slice-local version contract. It records Agent contract version, context schema version, PatchPlan schema version, fixture schema version, evidence schema version, `flashDB_rust` crate version, Cargo.toml/Cargo.lock hashes, Rust/Cargo/Git/OpenSpec versions, FlashDB clone URL and commit, feature matrix, host OS, workspace branch/commit, and cache key inputs.

中文：每个切片最终验证证据必须引用 version manifest 的路径和 hash。若 manifest 中任一缓存键输入漂移，包括 FlashDB source commit、Cargo.lock、schema version、toolchain version、feature matrix、fixture hash 或 AI metadata，旧 ContextPack、PatchPlan、C oracle、diff 结论和 AI 候选补丁都不能直接复用。

## AI Version Rule

AI is not a source of truth. When AI is used, the run must record model/provider metadata, prompt/context hash, candidate patch hash, and the verification gates that accepted or rejected the candidate. Cached AI output is only a reusable candidate.

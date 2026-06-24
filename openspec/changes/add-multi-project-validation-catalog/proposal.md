## Why

当前只完成了 FlashDB 单项目的行为级验证闭环，还没有覆盖“十几个复杂 C 项目”的迁移验证目标。需要先建立可审计的项目目录、分层 gate 和证据格式，避免把候选名单或单次构建误当成完整迁移成功。

English summary: FlashDB is only the first target. This change creates a reusable multi-project validation catalog and probe gate for large C projects before deeper per-project migration work begins.

## What Changes

- Add a versioned validation catalog with at least 12 complex C/C-major projects across storage, networking, crypto, media, database, runtime, allocator, and systems domains.
- Add L0-L3 validation gates that separate remote reachability, native build/test smoke, bounded C-to-Rust migration slices, and differential/performance evidence.
- Add a lightweight local PowerShell verifier that validates catalog shape and can optionally probe remote repository HEADs without cloning large projects.
- Add durable probe evidence under `validation/evidence/`.
- Document that this is a validation-planning and probe milestone, not proof that all listed projects have been migrated.

## Capabilities

### New Capabilities

- `multi-project-validation-catalog`: Covers the catalog, per-project validation metadata, L0-L3 gates, no-clone probe evidence, and non-equivalence-claim boundaries.

### Modified Capabilities

- None.

## Impact

- Adds `validation/` documentation, catalog data, and evidence files.
- Adds `scripts/validate-c-project-catalog.ps1` for fast catalog validation and optional remote probe.
- Adds OpenSpec artifacts for the multi-project validation milestone.
- Does not clone large external repositories into this repo.
- Does not claim C-to-Rust migration success for any catalog target until that target passes its own deeper gates.

## Why

当前自动翻译管线已经具备 slice spec、context pack、type map、CFG、pointer graph、编译自愈、C oracle/Rust replay/diff、unsafe ledger 与 OpenSpec evidence，但翻译前端仍主要依赖受限手写扫描和人工挑选 slice。它能诚实阻塞真实 FlashDB 函数，但还不能把 C2Rust/libclang 这类真实 C 前端产出的语义事实纳入统一路由、候选生成和验证门禁。

本 change 将把 `c2r-migration-pipeline-design.md` 中已确认的方案落成项目主线：用真实源码绑定、tree-sitter 句法层、libclang 语义事实、可选 C2Rust unsafe baseline、L0-L4 路由、Agent 候选生成和统一验证门禁，推动项目从“验证基础设施 + 受限手写翻译”进入“C2Rust 参考前端 + Agent 可用迁移管道”的阶段。

## What Changes

- Add a C2Rust/libclang baseline integration path that can record C2Rust availability, command inputs, output paths, baseline hashes, and unsupported environment reasons without treating C2Rust output as correctness evidence.
- Add L0-L4 route-decision evidence to automatic migration runs, including routing level, translator choice, rationale, verification profile, and fail-closed blocked reasons.
- Refine the frontend contract: tree-sitter or syntax scanning may locate slices and syntax features, while libclang/compile profile/C2Rust baseline provide typed semantic facts when available.
- Update Agent candidate boundaries so Codex/OpenCode can consume compact context bundles, C2Rust baseline snippets, type facts, pointer graph facts, and structured repair hints while remaining unable to bypass verification gates.
- Add validation-profile evidence that ties required checks to route level and run goal, without hardcoding 10-round or 10000-round regression as a project requirement.
- Add implementation tasks for a minimum credible loop: one real FlashDB function gets machine-extracted, routed, given baseline/context evidence, translated or blocked, and bound into the existing L3 evidence manifest.

## Capabilities

### New Capabilities

- `c2rust-baseline-migration-pipeline`: Records the C2Rust/libclang-backed frontend, L0-L4 router, Agent candidate contract, validation profile, and incremental migration requirements that sit above the existing bounded automatic translation evidence model.

### Modified Capabilities

- `bounded-auto-translation-pipeline`: Existing automatic translation requirements will be extended so C2Rust baseline evidence, route decisions, validation profiles, and typed semantic facts become first-class L3 evidence inputs.

## Impact

- Affected OpenSpec areas: `bounded-auto-translation-pipeline` and the new `c2rust-baseline-migration-pipeline` capability.
- Affected implementation areas: `validation/tools/auto_migrate.py`, `validation/tools/extract_source_slice.py`, `crates/c2r-translator`, validation schema/tests, and future C2Rust/libclang adapter modules.
- Affected evidence: auto-translation manifests will gain route decision, baseline manifest, validation profile, and Agent candidate references.
- Tooling impact: `F:\agent\c2rust-master` is treated as a reference source tree and optional external frontend input; missing C2Rust/libclang tools must produce explicit skipped/blocked evidence, not false success.
- Safety impact: `unsafe` remains allowed only below the project budget of 10%, with ledger and audit evidence required for accepted runs.

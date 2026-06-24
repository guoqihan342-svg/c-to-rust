## Why

The existing FlashDB TSDB L3 slices validate main-path append/query/status behavior and deleted-status persistence, but they do not validate public TSDB error semantics. A small `tsdb-error-boundary` slice closes that gap without expanding into TSDB layout, clean, capacity pressure, or power-loss behavior.

现有 FlashDB TSDB L3 切片已经验证主路径 append/query/status 行为和 deleted 状态持久化，但尚未验证公开可见的 TSDB 错误语义。新增一个小的 `tsdb-error-boundary` 切片，可以补齐错误边界证据，同时不扩展到 TSDB 布局、clean、容量压力或掉电行为。

## What Changes

- Add a named L3 slice, `tsdb-error-boundary`, under the existing FlashDB L3 migration loop.
- Freeze a deterministic TSDB fixture covering unknown `entry_id` for `ts.set_status`, unknown status for `ts.count_status`, and valid TSDB behavior after those errors.
- Generate Rust replay, WSL/Linux/CI C oracle, schema-aware diff, negative diff, compile self-healing, unsafe, cache, performance smoke, and bilingual summary evidence under `validation/evidence/flashdb/`.
- Keep step `status`, step `code`, operation id, operation name, error semantics, `entry_id`, `timestamp`, `status`, `value`, and `count` as strict behavior fields.
- Keep code edits single-writer; parallel agents are used only for read-only Rust boundary review, C oracle boundary review, evidence audit, and patch review.
- No breaking changes to public Rust API are intended.

中文说明：本变更只增加一个命名 L3 错误边界切片和对应证据链。它使用同一 fixture 对 Rust replay 与 C oracle 进行 schema-aware diff，错误状态、错误码、操作身份和后续正常行为都不能被 accepted differences 掩盖。

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add TSDB public error-boundary validation, including C oracle parity, strict diff gates, evidence files, unsafe budget, cache invalidation, and bounded self-healing rules.

中文说明：修改 `flashdb-l3-agent-migration-loop` 能力，加入 TSDB 公开错误边界的严格 L3 验证门禁。

## Impact

- Rust fixture and tests under `flashDB_rust/fixtures/` and `flashDB_rust/tests/`.
- Existing Rust TSDB/replay code under `flashDB_rust/src/` only if tests expose a parity gap.
- Existing C oracle tooling under `flashDB_rust/oracle/`; no C oracle contract broadening is planned unless validation proves it is required.
- L3 evidence under `validation/evidence/flashdb/`.
- OpenSpec artifacts under `openspec/changes/run-flashdb-tsdb-error-boundary-l3-loop/`.
- No new runtime dependency, async runtime, or internal multithreading is planned.

中文说明：影响范围限制在 fixture、测试、证据和本 OpenSpec 变更目录。除非验证暴露语义差异，否则不修改 Rust 公共 API、不扩大 C oracle 合约、不引入 async runtime 或内部多线程。

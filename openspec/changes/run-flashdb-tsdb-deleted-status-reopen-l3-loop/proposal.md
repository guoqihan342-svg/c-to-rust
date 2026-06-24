## Why

The existing TSDB L3 slice validates append/query, `user1` status update, count-by-status, and reopen, but it does not validate the `deleted` status even though both Rust replay and the C oracle already support it. A small `deleted` status slice increases semantic confidence without expanding into TSDB clean, sector rollover, payload limits, or storage-layout claims.

现有 TSDB L3 切片已经验证 append/query、`user1` 状态更新、按状态计数和 reopen，但尚未独立验证 `deleted` 状态。新增一个小而明确的 `deleted` 状态切片，可以提升语义等价证据，同时不扩展到 TSDB clean、扇区滚转、负载长度或存储布局等范围。

## What Changes

- Add a named L3 slice, `tsdb-deleted-status-reopen`, under the existing FlashDB L3 migration loop.
- Freeze a deterministic TSDB fixture covering two appends, setting entry 1 to `deleted`, counting `deleted` and `written`, reopening, and recounting `deleted`.
- Generate Rust replay, WSL/Linux/CI C oracle, schema-aware diff, negative diff, compile self-healing, unsafe, cache, performance smoke, and bilingual summary evidence under `validation/evidence/flashdb/`.
- Keep `entry_id`, `timestamp`, `status`, `value`, `count`, step `status`, step `code`, operation id, and operation name as strict behavior fields.
- Keep single-writer patching; parallel agents are used only for read-only slice review, C oracle boundary review, evidence audit, and patch review.
- No breaking changes to public Rust API are intended.

中文说明：本变更只增加一个命名 L3 切片和对应证据链，使用同一 fixture 对 Rust replay 与 C oracle 进行 schema-aware diff。行为字段不允许进入 accepted differences；代码补丁仍由单写者串行应用，多智能体只做只读审计和独立验证。

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add TSDB deleted-status plus reopen persistence as a strict L3 slice, including C oracle parity, diff gates, evidence files, unsafe budget, cache invalidation, and bounded self-healing rules.

中文说明：修改 `flashdb-l3-agent-migration-loop` 能力，加入 TSDB `deleted` 状态与 reopen 持久化的严格 L3 验证门禁。

## Impact

- Rust fixture and tests under `flashDB_rust/fixtures/` and `flashDB_rust/tests/`.
- Existing Rust TSDB/replay code under `flashDB_rust/src/` only if tests expose a parity gap.
- Existing C oracle tooling under `flashDB_rust/oracle/`; no C oracle contract broadening is planned unless validation proves it is required.
- L3 evidence under `validation/evidence/flashdb/`.
- OpenSpec artifacts under `openspec/changes/run-flashdb-tsdb-deleted-status-reopen-l3-loop/`.
- No new runtime dependency, async runtime, or internal multithreading is planned.

中文说明：影响范围限制在 fixture、测试、证据和本 OpenSpec 变更目录。除非验证暴露语义差异，否则不修改 Rust 公共 API、不扩大 C oracle 合约、不引入 async runtime 或内部多线程。

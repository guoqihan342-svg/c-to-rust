## Why

TSDB L3 evidence now covers append/query/status, deleted status, error boundaries, report-schema repair, `user2`, and repeated status transitions. The next small gap is payload boundary visibility: public callers need C/Rust evidence that an empty payload and the FlashDB C oracle maximum 128-byte payload remain queryable and persistent after reopen.

TSDB L3 证据已经覆盖 append/query/status、deleted status、错误边界、报告 schema 修复、`user2` 和连续状态转换。下一个小缺口是 payload 边界可见性：公共调用方需要 C/Rust 证据证明空 payload 和 FlashDB C oracle 的 128 字节最大 payload 在 query 与 reopen 后仍保持一致可见。

## What Changes

- Add a focused `tsdb-payload-boundary` L3 fixture that appends an empty payload record and a 128-byte ASCII payload record, then checks full-range query, exact timestamp query, empty range query, count-by-status, reopen, and query-after-reopen.
- 新增聚焦的 `tsdb-payload-boundary` L3 fixture：追加空 payload 记录和 128 字节 ASCII payload 记录，然后验证全范围 query、精确时间戳 query、空范围 query、按状态计数、reopen 以及 reopen 后 query。
- Add Rust replay/differential tests proving payload bytes are behavior fields and cannot be hidden by accepted metadata differences.
- 新增 Rust replay/differential 测试，证明 payload 字节属于行为字段，不能被 accepted metadata differences 掩盖。
- Generate Rust report, C oracle, schema diff, negative diff, compile check, unsafe scan, cache metadata, performance smoke, and bilingual summary evidence.
- 生成 Rust report、C oracle、schema diff、negative diff、编译检查、unsafe 扫描、缓存元数据、性能烟测和中英文 summary 证据。
- Do not claim over-limit payload rejection, binary or NUL payload behavior, capacity pressure, sector rollover/full, clean/GC, physical deletion, byte-for-byte layout, corrupt-image reopen, non-monotonic timestamps, or power-loss behavior.
- 不声明超限 payload 拒绝、二进制或 NUL payload 行为、容量压力、sector rollover/full、clean/GC、物理删除、字节级布局、损坏镜像 reopen、非递增时间戳或断电行为。

## Capabilities

### New Capabilities

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: add TSDB payload-boundary visible behavior as a focused L3 C/Rust replay slice.

## Impact

- `flashDB_rust/fixtures/l3-tsdb-payload-boundary.json`
- `flashDB_rust/tests/differential_replay.rs`
- `validation/evidence/flashdb/l3-tsdb-payload-boundary-*`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive

No public Rust API, storage layout, C FlashDB source, async runtime, threading model, or unsafe policy change is intended.

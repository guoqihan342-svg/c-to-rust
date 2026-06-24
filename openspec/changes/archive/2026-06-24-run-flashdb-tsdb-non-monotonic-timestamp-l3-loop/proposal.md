## Why

TSDB append/query/status slices already prove successful monotonic appends, status transitions, payload limits, reverse query, and reopen persistence. They explicitly do not prove the C FlashDB rule that every `fdb_tsl_append_with_ts` timestamp must be strictly greater than the last successful timestamp; Rust currently needs a focused L3 gate for duplicate and decreasing timestamp rejection.

已有 TSDB append/query/status 切片已经证明了成功的递增 append、状态迁移、payload 边界、反向查询和 reopen 持久化。但它们明确没有证明 C FlashDB 的规则：每次 `fdb_tsl_append_with_ts` 的 timestamp 必须严格大于上一次成功写入的 timestamp；Rust 当前需要一个聚焦的 L3 闸门来覆盖重复 timestamp 与倒退 timestamp 的拒绝语义。

## What Changes

- Add a focused `tsdb-non-monotonic-timestamp` L3 fixture that appends one valid control record, attempts one duplicate timestamp append and one decreasing timestamp append, verifies both report `status:"error"` with `code:"FDB_WRITE_ERR"`, appends a later valid record, queries/counts visible state, reopens, and verifies state again.
- 新增聚焦的 `tsdb-non-monotonic-timestamp` L3 fixture：先追加一条有效对照记录，再尝试重复 timestamp append 和倒退 timestamp append，验证两者都报告 `status:"error"` 与 `code:"FDB_WRITE_ERR"`，随后追加一条更晚的有效记录，查询/计数可见状态，reopen 后再次验证状态。
- Add Rust replay/differential tests proving timestamp-order error codes, failed-append non-visibility, contiguous successful entry ids, query entries, counts, and reopen persistence remain strict behavior fields.
- 新增 Rust replay/differential 测试，证明 timestamp 顺序错误码、失败 append 不可见、成功记录 `entry_id` 连续、query entries、count 和 reopen 持久化都是严格行为字段。
- Align `TsDb::append` with C FlashDB strict-increasing timestamp semantics if the red test exposes a Rust gap.
- 如果红测暴露 Rust 缺口，则让 `TsDb::append` 对齐 C FlashDB 的 timestamp 严格递增语义。
- Generate Rust report, C oracle, schema diff, negative diff, compile check, unsafe scan, cache metadata, performance smoke, and bilingual summary evidence.
- 生成 Rust report、C oracle、schema diff、negative diff、编译检查、unsafe 扫描、缓存元数据、性能烟测与中英双语 summary 证据。
- Do not claim timestamp overflow, negative timestamp, sector rollover/full, clean/GC, physical deletion, byte-for-byte layout, corrupt-image reopen, payload-size behavior, async/threading, or power-loss behavior.
- 不声明 timestamp 溢出、负 timestamp、sector rollover/full、clean/GC、物理删除、字节级布局、损坏镜像 reopen、payload-size 行为、异步/多线程或断电行为。

## Capabilities

### New Capabilities

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: add TSDB strict-increasing timestamp append rejection as a focused L3 C/Rust replay slice.

## Impact

- `flashDB_rust/fixtures/l3-tsdb-non-monotonic-timestamp.json`
- `flashDB_rust/tests/differential_replay.rs`
- `flashDB_rust/src/tsdb.rs` if Rust replay does not yet enforce FlashDB's strictly increasing TSDB timestamp rule
- `flashDB_rust/src/replay.rs` only if error-code mapping needs adjustment
- `flashDB_rust/oracle/flashdb_c_oracle.c` only if the C oracle does not yet serialize append errors from `fdb_tsl_append_with_ts`
- `validation/evidence/flashdb/l3-tsdb-non-monotonic-timestamp-*`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive

No public Rust API, storage layout, async runtime, threading model, or unsafe policy change is intended.

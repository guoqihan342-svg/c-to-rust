## Why

TSDB L3 evidence already proves reverse query before reopen and forward query after reopen. The next small gap is reverse query after reopen: public callers need C/Rust evidence that persisted TSDB entries still return in reverse time order after the database is reopened.

TSDB L3 证据已经证明 reopen 前反向 query 与 reopen 后正向 query。下一个小缺口是 reopen 后反向 query：公共调用方需要 C/Rust 证据证明 TSDB 持久化后再次打开，仍会按反向时间顺序返回记录。

## What Changes

- Add a focused `tsdb-reverse-query-reopen` L3 fixture that appends three timestamped records, changes the middle record to `user1`, checks reverse query before reopen, reopens the TSDB, and checks reverse query again.
- 新增聚焦的 `tsdb-reverse-query-reopen` L3 fixture：追加三条带时间戳的记录，将中间记录改为 `user1`，验证 reopen 前反向 query，reopen 后再次验证反向 query。
- Add Rust replay/differential tests proving query entry ordering, entry id, timestamp, status, and value remain strict behavior fields.
- 新增 Rust replay/differential 测试，证明 query entry 顺序、entry id、timestamp、status 和 value 都是严格行为字段。
- Generate Rust report, C oracle, schema diff, negative diff, compile check, unsafe scan, cache metadata, performance smoke, and bilingual summary evidence.
- 生成 Rust report、C oracle、schema diff、negative diff、编译检查、unsafe 扫描、缓存元数据、性能烟测和中英文 summary 证据。
- Do not claim reverse `count_status` semantics, capacity pressure, sector rollover/full, clean/GC, physical deletion, byte-for-byte layout, corrupt-image reopen, payload limits, non-monotonic timestamps, async/threading, or power-loss behavior.
- 不声明反向 `count_status` 语义、容量压力、sector rollover/full、clean/GC、物理删除、字节级布局、损坏镜像 reopen、payload limit、非递增时间戳、异步/多线程或断电行为。

## Capabilities

### New Capabilities

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: add TSDB reverse-query-after-reopen visible behavior as a focused L3 C/Rust replay slice.

## Impact

- `flashDB_rust/fixtures/l3-tsdb-reverse-query-reopen.json`
- `flashDB_rust/tests/differential_replay.rs`
- `validation/evidence/flashdb/l3-tsdb-reverse-query-reopen-*`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive

No public Rust API, storage layout, C FlashDB source, async runtime, threading model, or unsafe policy change is intended.

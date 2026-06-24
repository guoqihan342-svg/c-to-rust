## Why

TSDB L3 evidence now covers append/query/status, deleted status, error boundaries, `ts.set_status` report-schema repair, and `user2`. The next small gap is repeated status transition on the same TS entry: public callers need the latest status to win across query, count, and reopen.

TSDB L3 证据已经覆盖 append/query/status、deleted、错误边界、`ts.set_status` 报告 schema 修复和 `user2`。下一个小缺口是同一条 TS entry 的连续状态转换：公共调用方需要确认最新状态会在 query、count 和 reopen 后生效。

## What Changes

- Add a focused `tsdb-status-transition` L3 fixture that appends two records, changes one entry through `user1 -> user2 -> deleted`, then checks count/query before and after reopen.
- 新增一个聚焦的 `tsdb-status-transition` L3 fixture：追加两条记录，将其中一条从 `user1 -> user2 -> deleted` 连续更新，然后在 reopen 前后验证 count/query。
- Add Rust replay/differential tests proving stale intermediate statuses do not remain visible.
- 新增 Rust replay/differential 测试，证明中间旧状态不会继续可见。
- Generate Rust report, C oracle, schema diff, negative diff, compile check, unsafe scan, cache metadata, performance smoke, and bilingual summary evidence.
- 生成 Rust report、C oracle、schema diff、negative diff、编译检查、unsafe 扫描、缓存元数据、性能烟测和中英文 summary 证据。
- Do not claim capacity pressure, sector rollover/full, clean/GC, physical deletion, byte-for-byte layout, corrupt-image reopen, payload limits, or power-loss behavior.
- 不声明容量压力、sector rollover/full、clean/GC、物理删除、字节级布局、损坏镜像 reopen、payload limit 或断电行为。

## Capabilities

### New Capabilities

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: add TSDB repeated status-transition visible behavior as a focused L3 C/Rust replay slice.

## Impact

- `flashDB_rust/fixtures/l3-tsdb-status-transition.json`
- `flashDB_rust/tests/differential_replay.rs`
- `validation/evidence/flashdb/l3-tsdb-status-transition-*`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive

No public Rust API, storage layout, C FlashDB source, async runtime, threading model, or unsafe policy change is intended.

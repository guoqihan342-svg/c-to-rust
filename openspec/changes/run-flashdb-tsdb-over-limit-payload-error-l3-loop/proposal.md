## Why

TSDB payload-boundary evidence already proves empty and exactly 128-byte ASCII payload visibility, but it explicitly excludes over-limit rejection. The next small public-visible gap is the 129-byte payload error boundary: callers need C/Rust evidence that an over-limit TSDB append fails with `FDB_WRITE_ERR`, does not create a visible record, and leaves later successful appends and reopen behavior stable.

TSDB payload-boundary 证据已经证明空 payload 与刚好 128 字节 ASCII payload 的可见性，但它明确排除了超限拒绝行为。下一个小而清晰的公开可见缺口是 129 字节 payload 错误边界：调用方需要 C/Rust 证据证明超限 TSDB append 会以 `FDB_WRITE_ERR` 失败，不会产生可见记录，并且后续成功 append 与 reopen 行为保持稳定。

## What Changes

- Add a focused `tsdb-over-limit-payload-error` L3 fixture that appends one valid control record, attempts one 129-byte ASCII `ts.append`, verifies `status:"error"` with `code:"FDB_WRITE_ERR"`, appends a later valid record, queries/counts visible state, reopens, and verifies state again.
- 新增聚焦的 `tsdb-over-limit-payload-error` L3 fixture：先追加一条有效对照记录，再尝试一条 129 字节 ASCII `ts.append`，验证 `status:"error"` 与 `code:"FDB_WRITE_ERR"`，随后追加一条有效记录，查询/计数可见状态，reopen 后再次验证状态。
- Add Rust replay/differential tests proving over-limit error code, failed-append non-visibility, contiguous successful entry ids, query entries, counts, and reopen persistence remain strict behavior fields.
- 新增 Rust replay/differential 测试，证明超限错误码、失败 append 不可见、成功记录 entry id 连续、query entries、count 与 reopen 持久性都是严格行为字段。
- Generate Rust report, C oracle, schema diff, negative diff, compile check, unsafe scan, cache metadata, performance smoke, and bilingual summary evidence.
- 生成 Rust report、C oracle、schema diff、negative diff、编译检查、unsafe 扫描、缓存元数据、性能烟测与中英双语 summary 证据。
- Do not claim binary or NUL payload handling, payloads larger than 129 bytes, capacity pressure, sector rollover/full, clean/GC, physical deletion, byte-for-byte layout, corrupt-image reopen, non-monotonic timestamps, async/threading, or power-loss behavior.
- 不声明 binary/NUL payload、超过 129 字节 payload、容量压力、sector rollover/full、clean/GC、物理删除、字节级布局、损坏镜像 reopen、非递增 timestamp、异步/多线程或断电行为。

## Capabilities

### New Capabilities

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: add TSDB over-limit payload error visible behavior as a focused L3 C/Rust replay slice.

## Impact

- `flashDB_rust/fixtures/l3-tsdb-over-limit-payload-error.json`
- `flashDB_rust/tests/differential_replay.rs`
- `flashDB_rust/src/tsdb.rs` if Rust replay does not yet enforce the FlashDB 128-byte TSDB payload limit
- `flashDB_rust/src/replay.rs` if error-code mapping needs adjustment
- `flashDB_rust/oracle/flashdb_c_oracle.c` if the C oracle does not yet emit append errors for over-limit payloads
- `validation/evidence/flashdb/l3-tsdb-over-limit-payload-error-*`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive

No public Rust API, storage layout, async runtime, threading model, or unsafe policy change is intended.

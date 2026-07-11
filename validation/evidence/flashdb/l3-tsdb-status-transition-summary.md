# FlashDB L3 TSDB Status Transition Slice Summary

## Result

Passed. The `tsdb-status-transition` slice validates that repeated status updates on the same TSDB entry expose only the latest public status through count, query, and reopen.

通过。`tsdb-status-transition` 切片验证了同一 TSDB entry 连续状态更新后，count、query 和 reopen 只暴露最新公共状态。

## Fixture

- Path: `flashDB_rust/fixtures/l3-tsdb-status-transition.json`
- Fixture hash: `9353686b`
- SHA-256: `d34e751396348bd1244a26c9edc7080d2299dc3c07f3a8248c5665ae9ed313f5`
- Operations: 17

The fixture appends two records, transitions entry 1 through `user1`, `user2`, and `deleted`, keeps entry 2 `written`, then verifies count/query before and after reopen.

该 fixture 追加两条记录，将 entry 1 依次更新为 `user1`、`user2`、`deleted`，保持 entry 2 为 `written`，并在 reopen 前后验证 count/query。

## Evidence

- Rust report: `validation/evidence/flashdb/l3-tsdb-status-transition-rust-report.json`
- C oracle: `validation/evidence/flashdb/l3-tsdb-status-transition-c-oracle.json`
- Diff: `validation/evidence/flashdb/l3-tsdb-status-transition-diff.json`
- Negative diff: `validation/evidence/flashdb/l3-tsdb-status-transition-negative-diff.json`
- Final verification: `validation/evidence/flashdb/l3-tsdb-status-transition-final-verification.json`

The negative diff mutates final query entry 1 from `status:"deleted"` to `status:"user2"` and fails at `steps.ts-tr-013.entries`.

负向 diff 将最终 query 中 entry 1 的 `status:"deleted"` 改为 `status:"user2"`，并在 `steps.ts-tr-013.entries` 被拦截。

## Safety And Build

- `cargo check --message-format=json`: passed, 0 compiler errors, 0 compiler warnings.
- `cargo test --test differential_replay status_transition -- --nocapture`: 2 passed, 0 failed.
- `cargo test`: passed.
- `cargo run -- unsafe-scan`: `unsafe_blocks:0`, `unsafe_fns:0`.
- `git diff --check`: passed.

## Non-Goals

No clean/GC, sector rollover/full, capacity pressure, byte-for-byte image layout, corrupt-image reopen, payload-boundary, payload limit, power-loss, async runtime, internal multithreading, public API, or unsafe policy change is claimed by this slice.

本切片不声明 clean/GC、sector rollover/full、容量压力、字节级镜像布局、损坏镜像 reopen、payload-boundary、payload limit、断电、异步运行时、内部多线程、公共 API 或 unsafe 策略变化。

## Next Slice

The next useful slice is `tsdb-payload-boundary`: validate empty and 128-byte ASCII payload visibility while excluding capacity, rollover, binary payload, and over-limit claims.

下一步建议做 `tsdb-payload-boundary`：验证空 payload 和 128 字节 ASCII payload 的可见性，同时排除容量、rollover、二进制 payload 和超限行为声明。

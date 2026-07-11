# FlashDB L3 TSDB Payload Boundary Summary

## English

Status: passed.

This slice validates `tsdb-payload-boundary` as a public-visible TSDB behavior slice. The fixture appends an empty payload and an exactly 128-byte ASCII payload, verifies full-range query, exact timestamp query, empty range query, written counts, reopen, and query-after-reopen. Rust replay and C oracle use the same fixture hash `441bcb21`.

The C oracle producer evidence records `C_ORACLE_GENERATED`. The schema-aware diff passed for the unmodified C/Rust reports. The negative diff mutates the final reopen query payload and fails as expected at `steps.ts-pb-009.entries`, proving payload value differences are strict behavior differences.


Non-goals remain out of scope: 129-byte rejection, binary or NUL payloads, capacity pressure, sector rollover/full, clean/GC, byte-for-byte layout, corrupt-image reopen, non-monotonic timestamps, and power-loss behavior.

## 中文

状态：通过。

本切片验证 `tsdb-payload-boundary` 作为公开可见的 TSDB 行为切片。fixture 追加一条空 payload 和一条刚好 128 字节 ASCII payload，并验证全范围 query、精确时间戳 query、空范围 query、written 计数、reopen 以及 reopen 后 query。Rust replay 和 C oracle 使用同一个 fixture hash `441bcb21`。

C oracle producer evidence 记录了 `C_ORACLE_GENERATED`。未变异的 C/Rust report 通过 schema-aware diff。负向 diff 修改最终 reopen query 中的 payload，并按预期在 `steps.ts-pb-009.entries` 失败，证明 payload value 差异属于严格行为差异。


非目标仍然排除：129 字节拒绝、二进制或 NUL payload、容量压力、sector rollover/full、clean/GC、字节级布局、损坏镜像 reopen、非递增时间戳和断电行为。

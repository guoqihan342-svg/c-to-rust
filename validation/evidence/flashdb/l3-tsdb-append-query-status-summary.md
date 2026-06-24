# FlashDB L3 TSDB Append/Query/Status Summary

中文：`tsdb-append-query-status` 命名切片已完成 L3 行为证据闭环。Rust replay 与 WSL 生成的 C oracle 使用同一 fixture hash `2ea6ffb0`，schema-aware diff 通过且 `first_mismatch` 为 `null`。该结论只覆盖 `l3-tsdb-append-query-status.json` 中的 TSDB 行为字段，不声明 FlashDB 全库迁移完成，也不声明 byte-for-byte flash image layout 等价。

English: the `tsdb-append-query-status` named slice has completed the L3 behavior evidence loop. Rust replay and the WSL-generated C oracle use the same fixture hash `2ea6ffb0`; the schema-aware diff passed with `first_mismatch: null`. This claim is limited to the TSDB behavior fields in `l3-tsdb-append-query-status.json`; it does not claim full FlashDB migration or byte-for-byte flash image layout equivalence.

Evidence:

- C oracle: `validation/evidence/flashdb/l3-tsdb-append-query-status-c-oracle.json`, `toolchain_status: C_ORACLE_GENERATED`
- Rust report: `validation/evidence/flashdb/l3-tsdb-append-query-status-rust-report.json`
- Diff: `validation/evidence/flashdb/l3-tsdb-append-query-status-diff.json`, `status: passed`
- Negative diff: `validation/evidence/flashdb/l3-tsdb-append-query-status-negative-diff.json`, rejects `steps.ts-l3-006.count`
- Unsafe: 0 first-party non-test unsafe findings
- Performance smoke: TSDB L3 replay recorded as secondary evidence

Boundaries:

- Covered: strictly increasing timestamp append, forward query, reversed query, status update, count-by-status, reopen, and query-after-reopen.
- Not covered: non-monotonic timestamp rejection, max payload length, sector rollover/full, `fdb_tsl_clean`, and byte-for-byte flash image layout.

Next: KVDB compact/overwrite as visible behavior, or a larger KVDB GC/sector-layout design if native compact semantics are required.

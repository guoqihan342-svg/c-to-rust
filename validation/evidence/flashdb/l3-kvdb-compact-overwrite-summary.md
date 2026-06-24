# FlashDB KVDB Compact/Overwrite L3 Summary

## 中文

状态：passed。

本切片只验证 `kvdb-compact-overwrite` 的可见行为：同 key overwrite 后读取最新值、entries 只保留 live key 和最新值、`kv.compact` 前后行为不变、compact 后 reopen 仍保留最新值、delete 后 missing get 返回 null。

边界：本切片不证明原生 FlashDB GC、sector movement、tombstone layout、byte-for-byte flash image、掉电恢复、容量压力 compact 或 TSDB 等价。当前 C oracle 的 `kv.compact` 是 metadata/image_hash accepted-difference 步骤，正确性由 compact/reopen 前后的 `kv.get`、`kv.entries`、`kv.delete` 行为保证。

关键证据：
- Rust replay: `validation/evidence/flashdb/l3-kvdb-compact-overwrite-rust-report.json`
- C oracle: `validation/evidence/flashdb/l3-kvdb-compact-overwrite-c-oracle.json`, `toolchain_status=C_ORACLE_GENERATED`
- Diff: `validation/evidence/flashdb/l3-kvdb-compact-overwrite-diff.json`, `first_mismatch=null`
- Negative diff: `validation/evidence/flashdb/l3-kvdb-compact-overwrite-negative-diff.json`, 首个 mismatch 为 `steps.kv-co-010.value`
- Final verification: `validation/evidence/flashdb/l3-kvdb-compact-overwrite-final-verification.json`
- Unsafe: first-party non-test unsafe 为 0

## English

Status: passed.

This slice verifies only visible behavior for `kvdb-compact-overwrite`: latest value after same-key overwrite, live entries with latest values, stable behavior around `kv.compact`, persistence after reopen, and null read after delete.

Boundary: this slice does not prove native FlashDB GC, sector movement, tombstone layout, byte-for-byte flash image equivalence, power-loss recovery, capacity-pressure compaction, or TSDB equivalence. The current C oracle treats `kv.compact` as metadata/image_hash accepted difference, while correctness is gated by `kv.get`, `kv.entries`, and `kv.delete` behavior around compact/reopen.

Source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
Fixture hash: `78e5ef24`
Rust unsafe ratio: `0`
Performance smoke: `569 ms` for `14` operations, secondary only.

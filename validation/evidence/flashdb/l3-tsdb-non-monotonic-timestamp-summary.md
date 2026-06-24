# FlashDB L3 TSDB Non-Monotonic Timestamp Summary

Passed. The `tsdb-non-monotonic-timestamp` slice validates FlashDB TSDB strict timestamp ordering through Rust replay, C oracle generation, schema-aware diff, negative diff, compile check, unsafe scan, and OpenSpec validation.

通过。`tsdb-non-monotonic-timestamp` 切片已通过 Rust replay、C oracle 生成、schema-aware diff、负向 diff、编译检查、unsafe 扫描和 OpenSpec 验证，确认 FlashDB TSDB 的 timestamp 严格递增语义。

## Behavior

- Duplicate timestamp append returns `FDB_WRITE_ERR`.
- Decreasing timestamp append returns `FDB_WRITE_ERR`.
- Rejected appends do not create visible entries or consume successful entry ids.
- A later valid append, query/count, and reopen remain stable.

## 行为

- 重复 timestamp append 返回 `FDB_WRITE_ERR`。
- 倒退 timestamp append 返回 `FDB_WRITE_ERR`。
- 被拒绝的 append 不产生可见 entry，也不消耗成功记录的 entry id。
- 后续有效 append、query/count 与 reopen 仍保持稳定。

## Evidence

- Rust report: `validation/evidence/flashdb/l3-tsdb-non-monotonic-timestamp-rust-report.json`
- C oracle: `validation/evidence/flashdb/l3-tsdb-non-monotonic-timestamp-c-oracle.json`
- Positive diff: `validation/evidence/flashdb/l3-tsdb-non-monotonic-timestamp-diff.json`
- Negative diff: `validation/evidence/flashdb/l3-tsdb-non-monotonic-timestamp-negative-diff.json`
- Final verification: `validation/evidence/flashdb/l3-tsdb-non-monotonic-timestamp-final-verification.json`

## Next Candidate

KVDB missing-key delete should be the next focused L3 bugfix candidate. Parallel review found likely C/Rust error-code divergence around `fdb_kv_del` for missing keys.

## 下一候选

KVDB missing-key delete 应作为下一个聚焦 L3 bugfix 候选。并行审查发现 `fdb_kv_del` 对 missing key 的错误码语义可能与当前 Rust 行为存在差异。

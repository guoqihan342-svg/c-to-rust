# FlashDB TSDB Reverse Query Reopen L3 Summary

## English

- Change: `run-flashdb-tsdb-reverse-query-reopen-l3-loop`
- Slice: `tsdb-reverse-query-reopen`
- Fixture: `flashDB_rust/fixtures/l3-tsdb-reverse-query-reopen.json`
- Result: passed.
- Coverage: append timestamps `10`, `20`, `30`; update entry `2` to `user1`; reverse query before reopen; reopen; reverse query after reopen with entries ordered `30 -> 20 -> 10`.
- C/Rust diff: passed with the same fixture hash `1e0a2914`.
- Negative diff: rejected mutated after-reopen forward ordering at `steps.ts-rqr-007.entries`.
- Compiler/self-healing: `cargo check --message-format=json` had 0 errors and 0 warnings; no self-healing patch was needed.
- Unsafe: first-party non-test unsafe remains 0%, below the 10% requirement.
- Performance smoke: replay completed in 357 ms; performance is recorded as secondary evidence only.

## 中文

- 变更：`run-flashdb-tsdb-reverse-query-reopen-l3-loop`
- 切片：`tsdb-reverse-query-reopen`
- Fixture：`flashDB_rust/fixtures/l3-tsdb-reverse-query-reopen.json`
- 结果：通过。
- 覆盖范围：追加时间戳 `10`、`20`、`30`；将 entry `2` 更新为 `user1`；reopen 前反向 query；reopen；reopen 后反向 query 仍按 `30 -> 20 -> 10` 返回。
- C/Rust 差分：同一 fixture hash `1e0a2914` 下通过。
- 负向差分：篡改 reopen 后查询顺序为正向时，在 `steps.ts-rqr-007.entries` 被拦截。
- 编译/自愈：`cargo check --message-format=json` 为 0 error、0 warning；本切片不需要自动补丁自愈。
- Unsafe：一方非测试 unsafe 仍为 0%，低于 10% 要求。
- 性能烟测：replay 用时 357 ms；性能仅作为辅助证据，不替代语义正确性。

## Evidence

- `validation/evidence/flashdb/l3-tsdb-reverse-query-reopen-rust-report.json`
- `validation/evidence/flashdb/l3-tsdb-reverse-query-reopen-c-oracle.json`
- `validation/evidence/flashdb/l3-tsdb-reverse-query-reopen-diff.json`
- `validation/evidence/flashdb/l3-tsdb-reverse-query-reopen-negative-diff.json`
- `validation/evidence/flashdb/l3-tsdb-reverse-query-reopen-final-verification.json`

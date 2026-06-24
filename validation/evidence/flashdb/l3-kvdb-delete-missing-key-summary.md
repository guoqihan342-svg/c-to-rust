# FlashDB L3 KVDB Delete Missing Key Summary

## 中文

- 切片：`kvdb-delete-missing-key`
- 范围：合法但不存在的 `kv.delete` 必须返回 `FDB_KV_NAME_ERR`；missing `kv.get` 保持 `OK/null`。
- Fixture：`flashDB_rust/fixtures/l3-kvdb-delete-missing-key.json`
- Fixture hash：`7b2db3e1`
- C oracle：`C_ORACLE_GENERATED`
- C/Rust diff：`passed`
- Negative diff：`failed`，首个 mismatch：`steps.kv-dmk-001.code`
- Unsafe：first-party non-test unsafe ratio `0`，低于 10% 预算。
- 性能烟测：file backend 回放 `13` 个操作，耗时 `307.668 ms`。
- 关键红测：修复前 `kv-dmk-001` 仍返回成功；修复后 `kv-dmk-001` 和 `kv-dmk-008` 都返回 `FDB_KV_NAME_ERR`。

## English

- Slice: `kvdb-delete-missing-key`
- Scope: valid but absent `kv.delete` returns `FDB_KV_NAME_ERR`; missing `kv.get` remains `OK/null`.
- Fixture: `flashDB_rust/fixtures/l3-kvdb-delete-missing-key.json`
- Fixture hash: `7b2db3e1`
- C oracle: `C_ORACLE_GENERATED`
- C/Rust diff: `passed`
- Negative diff: `failed`, first mismatch: `steps.kv-dmk-001.code`
- Unsafe: first-party non-test unsafe ratio `0`, below the 10% budget.
- Performance smoke: file backend replayed `13` operations in `307.668 ms`.
- Key red test: before the fix, `kv-dmk-001` still reported success; after the fix, both `kv-dmk-001` and `kv-dmk-008` return `FDB_KV_NAME_ERR`.

## Context

FlashDB C implements `fdb_kv_del()` through `del_kv(db, key, NULL, true)`. When `find_kv()` cannot find a valid key, `del_kv()` returns `FDB_KV_NAME_ERR`; the C oracle already serializes that return code as `status:"error"` and `code:"FDB_KV_NAME_ERR"` for `kv.delete`.

FlashDB C 通过 `del_kv(db, key, NULL, true)` 实现 `fdb_kv_del()`。当 `find_kv()` 找不到合法 key 时，`del_kv()` 返回 `FDB_KV_NAME_ERR`；现有 C oracle 已经会把这个返回码序列化为 `kv.delete` 的 `status:"error"` 与 `code:"FDB_KV_NAME_ERR"`。

The current Rust `KvDb::delete` validates the key, always appends a delete record, removes the key from the in-memory map, and returns `Ok(())`. That preserves existing-key delete but makes valid missing-key delete incorrectly idempotent. `KvDb::get` already matches C-visible replay behavior for missing keys by returning `OK` with `null`, and that behavior is not part of this fix.

## Goals / Non-Goals

**Goals:**

- Freeze one named L3 slice: `kvdb-delete-missing-key`.
- Prove that `kv.delete` on a valid but currently missing key returns `FDB_KV_NAME_ERR`.
- Cover both never-existing delete and delete-after-delete as public visible error paths.
- Preserve missing `kv.get` behavior as `OK` with `null`.
- Preserve existing-key `kv.delete` success behavior when used as setup for delete-after-delete.
- Generate Rust replay and WSL/Linux/CI C oracle reports from the same fixture and compare them with schema-aware diff.
- Add negative diff coverage proving missing-delete `status` and `code` cannot be accepted differences.
- Keep first-party non-test unsafe at 0% for this slice.
- Reuse the established compile self-healing, cache, unsafe, performance, and summary evidence formats.

**Non-Goals:**

- Do not cover empty-key or overlong-key `kv.delete`; those belong in a future invalid-delete slice.
- Do not re-open the existing `kvdb-error-boundary`, `kvdb-compact-overwrite`, or `kvdb-lifecycle` fixture hashes.
- Do not claim native FlashDB GC, tombstone layout, sector movement, capacity pressure, byte-for-byte image layout, or power-loss recovery.
- Do not change the C oracle contract, accepted-difference behavior fields, replay schema, public fixture parser shape, async runtime, or internal multithreading.
- Do not treat diagnostic message text as a strict correctness field; `status` and `code` carry the behavior contract.

## Decisions

1. **Use a new L3 fixture instead of mutating older fixtures.**
   The fixture `flashDB_rust/fixtures/l3-kvdb-delete-missing-key.json` preserves archived fixture hashes and keeps this slice independently reproducible.

2. **Check existence before writing the delete tombstone.**
   `KvDb::delete` will validate key syntax first. If the key is valid but absent from `entries`, it will return an error mapped to `FDB_KV_NAME_ERR` without appending a record. Existing-key delete still appends `KvDelete`, removes the key, and returns success.

3. **Add one Rust error variant for FlashDB KV name errors.**
   The replay layer already serializes errors through `err.code()`, so a dedicated `Error` variant with code `FDB_KV_NAME_ERR` keeps the change local to Rust API semantics and avoids replay-specific branching.

4. **Keep missing get out of the fix.**
   The fixture may read a missing key before or after delete to prove recovery state, but `kv.get` remains a normal `OK/null` path and is not interpreted as an error.

5. **Use bounded parallelism for review only.**
   Parallel agents may inspect C semantics, Rust impact, evidence naming, and final review. Code edits remain single-writer to avoid conflicting patches.

## Risks / Trade-offs

- **Existing Rust tests may rely on idempotent delete** -> Update those tests to create the key before deleting it, or assert the new error when the test is specifically about missing delete.
- **Diagnostic messages differ between C and Rust** -> Keep `message` in accepted differences and assert behavior through `status` and `code`.
- **Changing `delete` before red test would hide the regression** -> Add fixture and differential replay test first, run the targeted test, and store red evidence before production code changes.
- **A repair could accidentally broaden accepted differences** -> Treat `status`, `code`, `value`, `entries`, operation id, and operation success as forbidden accepted-difference fields.
- **Delete-after-delete requires one existing delete setup step** -> The setup delete is not a new general lifecycle claim; the asserted behavior is the second delete returning `FDB_KV_NAME_ERR`.

## Migration Plan

1. Add the dedicated fixture and tests first, then run the targeted test to capture the expected failure.
2. Add the minimal Rust error mapping and missing-delete guard.
3. Rerun targeted tests, C/Rust replay, schema diff, unsafe scan, OpenSpec validation, and full Rust tests.
4. If any new compiler or test error appears, classify it into evidence, patch only the affected Rust files, and rerun the failed gate before broad validation.

## Open Questions

- None for this slice. C behavior, Rust gap, fixture naming, and evidence naming have been bounded by read-only review.

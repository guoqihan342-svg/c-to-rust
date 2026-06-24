## Why

KVDB L3 evidence already covers lifecycle, compact/overwrite, and basic error boundaries, but it still does not prove the C public API behavior for deleting a key that never existed or was already deleted. FlashDB C returns `FDB_KV_NAME_ERR` for this path, while the current Rust `KvDb::delete` treats it as success, so this is a small but behavior-visible parity gap worth closing now.

KVDB L3 证据已经覆盖生命周期、compact/overwrite 和基础错误边界，但还没有证明 C 公共 API 在删除从未存在或已删除 key 时的行为。FlashDB C 在该路径返回 `FDB_KV_NAME_ERR`，而当前 Rust `KvDb::delete` 会把它当作成功处理，因此这是一个小而明确的可见行为等价缺口，需要现在关闭。

## What Changes

- Add one named L3 slice, `kvdb-delete-missing-key`, under the existing FlashDB L3 migration loop.
- Add a dedicated fixture `flashDB_rust/fixtures/l3-kvdb-delete-missing-key.json` instead of mutating archived error-boundary fixtures, preserving older fixture hashes and evidence provenance.
- Cover both never-existing delete and delete-after-delete, plus recovery through set/get/delete/get/reopen/entries.
- Add Rust differential replay tests and a negative diff regression proving `status` and `code` changes on missing delete cannot be hidden by accepted differences.
- Add the minimum Rust API error mapping required for C parity: valid but missing `KvDb::delete` returns `FDB_KV_NAME_ERR`; missing `KvDb::get` remains `OK` with `null`.
- Generate Rust replay, WSL/Linux/CI C oracle, schema-aware diff, negative diff, compile self-healing, unsafe, cache, performance smoke, and bilingual summary evidence under `validation/evidence/flashdb/`.
- Keep single-writer patching; parallel agents are used only for read-only semantic review, Rust impact review, evidence audit, and post-patch review.
- No breaking dependency, async runtime, internal multithreading, GC, or byte-for-byte sector-layout claim is introduced.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add KVDB missing-key delete as a visible-error-semantics L3 slice, including C oracle parity, diff gates, evidence files, unsafe budget, deterministic cache invalidation, and bounded self-healing rules.

## Impact

- Rust fixture and tests under `flashDB_rust/fixtures/` and `flashDB_rust/tests/`.
- Minimal Rust implementation impact under `flashDB_rust/src/types.rs` and `flashDB_rust/src/kvdb.rs`; `flashDB_rust/src/replay.rs` should only need existing `err.code()` propagation.
- Existing persistence tests under `flashDB_rust/tests/` may need to stop relying on missing delete as success.
- Existing C oracle tooling under `flashDB_rust/oracle/`; no C oracle contract broadening is planned because `FDB_KV_NAME_ERR` is already serialized.
- L3 evidence under `validation/evidence/flashdb/`.
- OpenSpec artifacts under `openspec/changes/run-flashdb-kvdb-delete-missing-key-l3-loop/`.

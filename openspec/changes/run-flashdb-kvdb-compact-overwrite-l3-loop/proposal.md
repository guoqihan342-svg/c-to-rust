## Why

The first KVDB L3 slice explicitly left compact and overwrite semantics as a known gap, and the TSDB L3 slice has now proven the same evidence loop on another module. The next small, high-value slice is KVDB overwrite plus compact plus reopen as public visible behavior, while deliberately excluding native FlashDB GC and byte-for-byte sector layout claims.

第一个 KVDB L3 切片已经明确把 compact 与 overwrite 语义列为已知缺口，TSDB L3 切片也已证明同一套证据闭环可以跨模块复用。下一个小而有价值的切片是 KVDB overwrite、compact、reopen 的公开可见行为等价，但必须明确排除原生 FlashDB GC 与 byte-for-byte sector layout 声明。

## What Changes

- Add a third named L3 slice, `kvdb-compact-overwrite`, under the existing FlashDB L3 migration loop.
- Freeze a deterministic KVDB fixture covering same-key overwrite, latest-value get, entries after overwrite, compact as metadata-only step, reopen after compact, and delete/missing-get behavior.
- Generate Rust replay, WSL/Linux/CI C oracle, schema-aware diff, negative diff, compile self-healing, unsafe, cache, performance smoke, and bilingual summary evidence under `validation/evidence/flashdb/`.
- Keep `kv.compact` scoped to visible behavior: it may be represented as an accepted metadata/image-hash step, but behavior fields before and after compact/reopen must remain non-ignorable.
- Keep single-writer patching; parallel agents are used only for read-only slice review, C oracle boundary review, and evidence audit.
- No breaking changes to public Rust API are intended.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add KVDB compact/overwrite as a visible-behavior L3 slice, including C oracle parity, diff gates, evidence files, unsafe budget, cache invalidation, and bounded self-healing rules.

## Impact

- Rust fixture and tests under `flashDB_rust/fixtures/` and `flashDB_rust/tests/`.
- Existing Rust KVDB/replay code under `flashDB_rust/src/` only if tests expose a parity gap.
- Existing C oracle tooling under `flashDB_rust/oracle/`; no C oracle contract broadening is planned unless validation proves it is required.
- L3 evidence under `validation/evidence/flashdb/`.
- OpenSpec artifacts under `openspec/changes/run-flashdb-kvdb-compact-overwrite-l3-loop/`.
- No new runtime dependency, async runtime, or internal multithreading is planned.

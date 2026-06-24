## Context

FlashDB Rust already supports KVDB set/get/delete/entries/compact/reopen behavior in `flashDB_rust/src/kvdb.rs`, and the existing replay layer supports `kv.compact`, `kv.entries`, and `kv.reopen`. The first KVDB L3 slice, `kvdb-lifecycle`, intentionally omitted compact and same-key overwrite behavior; this change closes that visible-behavior gap without claiming native FlashDB GC or byte-for-byte sector layout parity.

FlashDB Rust 当前已经在 `flashDB_rust/src/kvdb.rs` 支持 KVDB set/get/delete/entries/compact/reopen，replay 层也支持 `kv.compact`、`kv.entries`、`kv.reopen`。第一个 KVDB L3 切片 `kvdb-lifecycle` 有意没有覆盖 compact 与同 key overwrite；本变更只关闭这个可见行为缺口，不声明原生 FlashDB GC 或 byte-for-byte sector layout 等价。

The C oracle can faithfully execute `kv.set`, `kv.get`, `kv.entries`, `kv.delete`, and `kv.reopen` through FlashDB public APIs. Its current `kv.compact` operation is metadata-only and returns an accepted image hash marker rather than invoking a native public compact API.

## Goals / Non-Goals

**Goals:**

- Freeze one named slice: `kvdb-compact-overwrite`.
- Validate same-key overwrite, latest-value reads, sorted live entries, compact step success, reopen after compact, and delete/missing-get behavior.
- Generate Rust replay and WSL/Linux/CI C oracle reports from the same fixture and compare them with schema-aware diff.
- Add negative diff coverage proving behavior fields such as `value`, `entries`, `status`, `code`, and operation success cannot be hidden by accepted differences.
- Keep first-party non-test unsafe at 0% for this slice.
- Reuse the established compile self-healing, cache, unsafe, performance, and summary evidence formats.

**Non-Goals:**

- Do not claim native FlashDB GC, internal compact, sector state, tombstone movement, or byte-for-byte flash image layout equivalence.
- Do not turn `kv.compact` image hash or layout output into a correctness gate.
- Do not add async runtime, internal multithreading, or concurrency behavior.
- Do not refactor unrelated TSDB, flash, format, or CLI behavior unless required by the visible KVDB slice.
- Do not broaden accepted differences to include behavior fields.

## Decisions

1. **Use visible behavior as the compact boundary.**
   The fixture will include `kv.compact`, but correctness is judged by `kv.get`, `kv.entries`, `kv.reopen`, and post-reopen reads/deletes. This matches the current C oracle capability and avoids overclaiming native GC semantics.

2. **Use a new L3 fixture instead of changing `kvdb-main.json`.**
   `flashDB_rust/fixtures/l3-kvdb-compact-overwrite.json` will make the L3 evidence boundary explicit and preserve older smoke fixtures.

3. **Keep behavior fields non-ignorable.**
   Accepted differences may include metadata such as `image_hash`, `backend`, `toolchain_status`, `source`, `fixture`, `fixture_hash`, and `report_path`. They must not include `value`, `entries`, `status`, `code`, operation success, or error semantics.

4. **Avoid capacity-pressure GC in this slice.**
   The fixture uses small ASCII keys and values to avoid forcing native FlashDB GC paths. A later `kvdb-gc-sector-layout` design can target sector-level compact behavior.

5. **Use bounded parallelism.**
   Parallel agents may review KVDB slice scope, C oracle boundaries, and evidence completeness. Code edits remain single-writer.

## Risks / Trade-offs

- **`kv.compact` is metadata-only in C oracle** -> The summary and slice contract must state that this slice proves visible behavior after compact/reopen, not native GC internals.
- **Diff allowlist could hide behavior drift** -> Tests and evidence must reject behavior-field accepted differences, especially `value` and `entries`.
- **Capacity pressure could trigger unmodeled GC** -> Keep fixture values small and defer space-pressure/sector movement to a separate design.
- **Existing diff has top-level metadata limitations** -> Summary must audit fixture hash and source commit for Rust and C reports.
- **Automatic repair could widen scope** -> PatchPlan evidence must block unsafe, public API changes outside impact set, C oracle contract changes, fixture behavior changes, or accepted-difference widening.

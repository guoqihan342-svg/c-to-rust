## Context

FlashDB Rust already supports KVDB `set`, `get`, `delete`, `entries`, `compact`, and `reopen`, and the C oracle validates keys for `kv.set`, `kv.get`, and `kv.delete` before calling FlashDB public APIs. Earlier L3 slices proved KVDB lifecycle, TSDB append/query/status, and KVDB compact/overwrite visible behavior. The remaining immediate gap is that the older broad abnormal fixture permits `code` as an accepted difference, which is too loose for L3 migration evidence.

FlashDB Rust 当前已经支持 KVDB `set`、`get`、`delete`、`entries`、`compact`、`reopen`，C oracle 也会在 `kv.set`、`kv.get`、`kv.delete` 调用 FlashDB public API 前执行 key 校验。此前 L3 切片已经验证 KVDB lifecycle、TSDB append/query/status、KVDB compact/overwrite 可见行为。当前最直接的缺口是旧的 broad abnormal fixture 允许 `code` 作为 accepted difference，这对 L3 迁移证据过于宽松。

## Goals / Non-Goals

**Goals:**

- Freeze one named slice: `kvdb-error-boundary`.
- Validate missing-key get, empty-key set, overlong-key set, and a valid set/get after error steps.
- Generate Rust replay and WSL/Linux/CI C oracle reports from the same fixture and compare them with schema-aware diff.
- Add negative diff coverage proving `status`, `code`, `value`, `key`, operation id, operation name, and operation success cannot be hidden by accepted differences.
- Keep first-party non-test unsafe at 0% for this slice.
- Reuse the established compile self-healing, cache, unsafe, performance, and summary evidence formats.

**Non-Goals:**

- Do not claim byte-for-byte flash image layout equivalence, native FlashDB GC, sector movement, tombstone layout, power-loss recovery, or capacity-pressure behavior.
- Do not change public Rust KVDB APIs unless validation exposes a strict parity bug.
- Do not broaden `abnormal.json` into the L3 source of truth.
- Do not use message text as the primary correctness field; machine-checkable `status`, `code`, and values are the gate.
- Do not add async runtime, internal multithreading, or concurrency behavior.
- Do not broaden accepted differences to include behavior fields.

## Decisions

1. **Use a new L3 fixture instead of changing `abnormal.json`.**
   `flashDB_rust/fixtures/l3-kvdb-error-boundary.json` makes the strict error-boundary contract explicit and avoids breaking older smoke or abnormal checks that are intentionally broader.

2. **Keep `code` and `status` non-ignorable.**
   Accepted differences may include metadata such as `image_hash`, `backend`, `toolchain_status`, `source`, `fixture`, `fixture_hash`, `report_path`, and optionally message text. They must not include `status`, `code`, `value`, `key`, step id, operation name, or operation success.

3. **Keep the first slice minimal.**
   The fixture covers `kv.get` missing key, `kv.set` empty key, `kv.set` overlong key, and valid set/get after the error path. `kv.delete` invalid-key and TSDB error boundaries are deferred to later slices so this loop can close quickly with clear evidence.

4. **Use C oracle public API boundary evidence.**
   The C oracle executes FlashDB public API behavior where possible and uses the same Rust-compatible key validation boundary for invalid-key cases. The summary must state that this validates public visible semantics, not internal FlashDB storage layout.

5. **Use bounded parallelism.**
   Parallel agents may review next-slice choice, C oracle boundary, and evidence completeness. Code edits remain single-writer to avoid conflicting patches.

## Risks / Trade-offs

- **Message strings may differ between C and Rust** -> Treat message as optional metadata; strict gates use `status`, `code`, and value behavior.
- **A narrow fixture may miss delete invalid-key behavior** -> Record it as a follow-up TSDB/KVDB error-boundary expansion, not part of this minimal slice.
- **Diff allowlist could hide the original bug class** -> Add both fixture assertions and a negative diff that mutates error `code` or `status`.
- **C oracle invalid-key behavior is partly adapter validation** -> Document the public boundary and keep the behavior contract focused on migrated API semantics rather than internal C error strings.
- **Automatic repair could widen scope** -> Patch evidence must block unsafe, public API changes outside impact set, C oracle contract changes, fixture behavior changes, or accepted-difference widening.

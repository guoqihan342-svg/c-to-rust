## Why

The previous L3 demo proved a bounded `out[0]` output pointer can be translated and validated, but it still avoids the common C API shape of reading from an input buffer with a length companion. The next useful step is a deterministic slice that combines `const int* values`, `len`, a bounded loop, and `out[0]` so the pipeline starts exercising pointer reads and pointer writes together.

上一轮已经把 `out[0]` 输出指针推进到 L3 evidence 闭环；现在需要补上真实 C API 更常见的 `const int* values + len` 只读输入 buffer 场景，并继续保持 safe Rust 边界、强验证和低成本回归。

## What Changes

- Add a `sum_i32_buffer(const int* values, int len, int* out)` demo slice covering bounded input-buffer reads and an output pointer write.
- Extend the bounded auto-translation evidence contract so CFG/pointer graph evidence records input buffer reads, length companion bounds, and safe public boundary decisions.
- Generate C oracle, Rust replay, schema diff, negative diff, unsafe scan, context pack, CFG, type map, pointer graph, test-translation, summary, cache/version evidence, and final verification for the new slice.
- Wire the new semantic evidence check into the cheap smoke/full-regression path without adding network or long-running stress requirements.
- Keep non-goals explicit: no NULL pointer execution, no aliasing proof, no arbitrary pointer arithmetic, no overflow-domain expansion, and no full-project migration claim.

## Capabilities

### New Capabilities
- `input-buffer-pointer-l3-demo-slice`: Defines the `sum_i32_buffer` L3 demo slice and its oracle/replay/evidence/regression behavior.

### Modified Capabilities
- `bounded-auto-translation-pipeline`: Adds required evidence for `const T* + len` input buffer reads, length-bound loop coverage, and safe Rust boundary decisions.

## Impact

- Affected code: `crates/c2r-translator/`, `validation/slice-specs/`, `validation/tools/auto_migrate.py`, `validation/tools/test_auto_migrate.py`, `validation/tools/validate_l2_evidence_summary.py`, `validation/l2_slices/`, `validation/evidence/`, `scripts/run-full-regression.ps1`.
- Affected evidence: new `sum-i32-buffer` C oracle, Rust replay, diff, negative diff, unsafe, manifest, auto-translation, pointer graph, and test-translation files under `validation/evidence/demo/`.
- No breaking changes: existing FlashDB, libuv, zlib, sqlite, and `store_add_one` evidence semantics remain unchanged.

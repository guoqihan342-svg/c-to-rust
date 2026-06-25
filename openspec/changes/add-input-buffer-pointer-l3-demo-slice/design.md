## Context

The repository now has a bounded translator, auto-translation evidence packages, `store_add_one` as a minimal `out[0]` L3 demo, and a one-round clean-evidence smoke gate. That proves output pointer writes can enter the L3 chain, but it still avoids the common C pattern where a `const T*` buffer is read under a length bound before writing a result through an output pointer.

当前目标不是扩大到任意 C99，也不是把 FlashDB 全库迁移完，而是继续把自动翻译能力从“输出指针”推进到“只读输入 buffer + 长度 companion + 输出指针”的可验证子集。

## Goals / Non-Goals

**Goals:**
- Add one deterministic `sum_i32_buffer(const int* values, int len, int* out)` demo slice.
- Prove the slice through C oracle, Rust replay, schema diff, negative diff, unsafe scan, pointer graph, type map, CFG, test translation, version/cache evidence, and full-regression smoke.
- Represent the Rust boundary as a safe API, for example an input slice and returned/report output value, without public raw pointers.
- Require pointer evidence to record `values` as a read-only input buffer, `len` as the companion bound, and `out[0]` as the write effect.
- Keep first-party unsafe usage at zero for this demo.

**Non-Goals:**
- No NULL pointer execution or equivalence claim.
- No aliasing proof between `values` and `out`.
- No arbitrary `values[i]` beyond a proven `0 <= i < len` loop.
- No pointer arithmetic such as `*(values + i)` or `*(out + i)`.
- No signed overflow expansion; fixture sums must stay in the C `int` defined range.
- No full-project migration claim.

## Decisions

1. Use `sum_i32_buffer` as the next demo slice.
   - Rationale: it adds input pointer reads, a length companion, a loop, and an output pointer while staying small enough to debug precisely.
   - Alternative: jump directly to a real project parser/compression slice; that would mix macro/type/alias/platform risks with the new buffer-read capability.

2. Treat `const int* values` as a safe Rust input slice at the public boundary.
   - Rationale: the C pointer is read-only and length-bounded by `len`; the public Rust API should expose `&[i32]` or an equivalent report input, not `*const i32`.
   - Alternative: generate raw pointer Rust and isolate it internally; that would expand unsafe and is unnecessary for this bounded demo.

3. Keep accepted semantics bound to C oracle plus checked Rust replay, not to the generated draft alone.
   - Rationale: the current pipeline deliberately distinguishes candidate Rust draft evidence from accepted replay evidence. This preserves correctness while the translator grows.
   - Alternative: promote the generated draft directly; this would make the claim stronger than the evidence supports.

4. Extend existing evidence validators instead of adding a parallel validation framework.
   - Rationale: `validate_auto_translation_evidence.py`, `validate_l2_evidence_summary.py`, test-translation coverage, and full-regression smoke already define the gate shape. New evidence should enter the same gates.
   - Alternative: write a slice-specific validator only; that would create a bypass path.

## Risks / Trade-offs

- [Risk] Array indexing translation accidentally accepts unbounded or negative indexes -> Mitigation: only accept `values[i]` when CFG evidence records a loop condition equivalent to `i < len` and the slice contract excludes negative `len`.
- [Risk] Signed overflow changes behavior -> Mitigation: fixture generator excludes cases whose sum exceeds `i32` range and records this in non-goals.
- [Risk] `values` and `out` alias in C but not Rust -> Mitigation: mark aliasing as a non-goal and require pointer graph to record `aliasing_proven: false` or equivalent unsupported alias note.
- [Risk] Evidence regeneration dirties committed evidence -> Mitigation: use stable `repo_commit: workspace` for static demo evidence and verify with `-RequireCleanEvidence` after commit.
- [Risk] Scope grows into generic pointer arithmetic -> Mitigation: explicitly reject `values[i]` outside len-bounded loops and keep `*(values + i)` out of scope.

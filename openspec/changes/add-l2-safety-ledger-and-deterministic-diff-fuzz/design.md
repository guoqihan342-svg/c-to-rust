## Context

`validation/l2_slices` currently validates three bounded pure-function slices: `sqlite-varint`, `zlib-adler32`, and `zstd-xxh32`. The crate already emits Rust reports, schema-aware diff reports, and `unsafe-scan.json`, but the L2 gate text requires an unsafe ledger and the existing L2 evidence does not prove that the L2 diff gate rejects an intentional mismatch.

The project constraints remain local-first, token-bounded, safe, fast, and small. This change hardens evidence for the existing L2 mechanism without expanding scope to full fuzzing, pointer dependency graphs, or macro translation.

## Goals / Non-Goals

**Goals:**

- Emit `validation/evidence/l2-slices/unsafe-ledger.json` for the L2 slice crate.
- Expand `zlib-adler32` from a small hand-picked fixture set to a bounded deterministic corpus.
- Emit `validation/evidence/l2-slices/zlib-adler32-negative-diff.json` proving L2 diff catches a mutated oracle value.
- Update `validation/evidence/l2-slices/l2-l3-summary.json` and `validation/gates.md` so the new evidence is visible and gate-aligned.
- Keep verification reproducible and dependency-free beyond the existing toolchain.

**Non-Goals:**

- Do not introduce `cargo-fuzz`, `proptest`, `quickcheck`, `arbitrary`, or another fuzz dependency.
- Do not implement pointer dependency graph extraction.
- Do not implement C macro activation-condition analysis.
- Do not productize the FlashDB L3 evidence template in this change.

## Decisions

- Use deterministic corpus generation instead of fuzz dependencies.
  - Rationale: the immediate gap is weak L2 corpus breadth, not absence of a fuzz engine. A fixed corpus gives reproducible evidence and keeps local validation fast.
  - Alternative considered: add `cargo-fuzz`. Rejected for this change because the host currently documents missing fuzz tooling and the project requirement favors small, fast gates first.

- Harden `zlib-adler32` first.
  - Rationale: it has only 7 current C oracle cases, a simple `&[u8] -> u32` surface, no seed argument, and no state.
  - Alternative considered: harden `zstd-xxh32` first. Deferred because seed coverage adds one more dimension and Adler32 gives a cleaner first gate.

- Treat unsafe ledger as an audit artifact, not just a scan copy.
  - Rationale: a zero unsafe count still needs durable evidence explaining scope, policy, audited modules, and whether any unsafe was registered.
  - Alternative considered: rely on `unsafe-scan.json`. Rejected because gate documentation explicitly calls for a ledger and future slices may require categorization.

- Generate one L2 negative diff first.
  - Rationale: one intentionally corrupted Adler32 oracle value proves the L2 diff path rejects mismatches. Requiring negative diff for all slices can be added after the pattern is stable.
  - Alternative considered: negative diff for all L2 slices now. Deferred to avoid expanding the change beyond the immediate evidence gap.

## Risks / Trade-offs

- [Risk] C oracle regeneration requires WSL/Linux paths and existing upstream build artifacts. -> Mitigation: keep Rust report generation independent and record regeneration commands; if oracle regeneration is unavailable, do not claim new C oracle evidence.
- [Risk] Large generated fixtures may slow tests or bloat the repository. -> Mitigation: cap Adler32 corpus at 137 cases and keep generated inputs deterministic.
- [Risk] Unsafe token scanning can over-count comments or strings. -> Mitigation: continue using the existing scanner that strips strings and line comments before token matching.
- [Risk] Negative diff could be misread as a failed migration. -> Mitigation: report `status:"passed"` only when the intentional mutation is detected, with a clear `mutation` field.


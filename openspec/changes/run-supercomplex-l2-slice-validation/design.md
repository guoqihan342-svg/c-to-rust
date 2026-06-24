## Context

The repository now has L0 catalog evidence and L1 native build/test evidence for 15 complex C/C-major projects. The next step is not broad project migration. It is a bounded L2/L3 pattern that proves the agent can translate narrow, named C logic into Rust, compile it, and compare behavior against C oracle fixtures.

The first slices are intentionally pure and dependency-light:

- SQLite varint encode/decode
- zlib-ng Adler-32 checksum
- zstd xxHash32 checksum

## Goals / Non-Goals

**Goals:**

- Add a small Rust crate under `validation/l2_slices` with first-party safe Rust implementations for the selected slices.
- Add tests before production implementation for each Rust slice.
- Generate C oracle fixtures from pinned L1 checkouts where possible.
- Produce per-slice evidence files for L2 Rust check and L3 C/Rust diff.
- Keep unsafe usage at 0 for the new Rust slice crate.

**Non-Goals:**

- Do not migrate complete SQLite, zlib-ng, or zstd.
- Do not claim semantic equivalence outside the named functions and fixture input domain.
- Do not vendor upstream source trees or generated build directories.
- Do not introduce async/threaded infrastructure for pure deterministic slices.

## Decisions

- Use a separate validation crate instead of extending `flashDB_rust`. This keeps FlashDB production code isolated from multi-project experiments.
- Use JSON fixtures and reports because they are small, stable, and easy to diff in CI or by scripts.
- Generate C oracle outputs through WSL and pinned L1 checkouts, then commit compact oracle reports rather than raw logs.
- Prefer pure functions first. These slices avoid ownership-heavy global state, event loops, allocation lifetimes, codec tolerance, and platform timing.
- Treat zstd, zlib-ng, and SQLite as independent slices so future agents can expand one project without breaking the others.

## Risks / Trade-offs

- [Risk] C oracle harnesses can accidentally test a different upstream revision. Mitigation: record commit SHA and source path in every evidence file.
- [Risk] Rust code can match the fixture corpus but still miss edge cases. Mitigation: include boundary values and malformed/truncated cases for format logic.
- [Risk] Handwritten Rust is not equivalent to automated C2Rust output. Mitigation: report it as bounded Rust slice migration, not full automated translation.
- [Risk] Tests may pass by comparing to hardcoded expected values rather than C oracle output. Mitigation: tests must load committed C oracle fixture JSON.

## Migration Plan

1. Add OpenSpec artifacts and validate the change.
2. Create `validation/l2_slices` crate and write failing tests against expected fixture-driven APIs.
3. Implement the three Rust slices after observing failing tests.
4. Generate C oracle fixtures from pinned external checkouts.
5. Run Rust tests and generate L2/L3 evidence.
6. Validate OpenSpec, Rust tests, and repository diff hygiene before commit/push.

## Open Questions

- Should the next wave prioritize more pure helpers from L1-passed projects or one larger parser/state-machine slice?
- Should long-term L2/L3 evidence move into a reusable CLI runner shared with FlashDB differential replay?

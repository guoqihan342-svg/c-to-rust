## Context

`add-flashdb-oracle-differential-harness` added a C oracle contract and CI workflow, but the current workflow does not configure `FLASHDB_C_ORACLE_PRODUCER`. As a result, Ubuntu CI can pass with `SKIPPED_C_ORACLE_PRODUCER_NOT_CONFIGURED`. That is acceptable for a transitional harness, but it is not enough for the user's goal of continuously closing migration gaps.

Current local Windows remains unable to build C because `gcc`, `clang`, `cl`, `make`, and `cmake` are absent. Therefore this change targets Ubuntu CI, where `gcc` is normally available.

## Goals / Non-Goals

**Goals:**

- Configure CI to call `flashDB_rust/oracle/generate_c_oracle.sh` by default.
- Make a configured C oracle producer failure fail the CI job.
- Keep missing `gcc` as the only normal CI skip path.
- Preserve Rust fmt/check/test/replay/diff/unsafe/stress gates.
- Record durable CI evidence for C oracle producer success or skip/failure.

**Non-Goals:**

- This change does not complete C/Rust report equivalence.
- This change does not install a native Windows C compiler.
- This change does not replace Rust fixture diff or 10000-loop stress.

## Decisions

### Decision 1: Configure producer in workflow env

Set `FLASHDB_C_ORACLE_PRODUCER=./oracle/generate_c_oracle.sh` in the workflow step that runs `scripts/verify-ci.sh`. This keeps the CI script reusable while making the repository default strict.

Alternative considered: hard-code the oracle script inside `verify-ci.sh`. Rejected because environment configuration keeps local and CI behavior explicit.

### Decision 2: Producer configured means failure is fatal

If `FLASHDB_C_ORACLE_PRODUCER` is set and the producer exits non-zero, CI MUST fail. The script may still write evidence before failing.

Alternative considered: keep `run_c_oracle_producer || true`. Rejected because it hides precisely the missing proof this change is meant to expose.

### Decision 3: C oracle generation evidence is separate from equivalence evidence

A successful C oracle producer proves that C FlashDB builds and emits oracle JSON. It does not by itself prove Rust equivalence until a later C/Rust schema-compatible diff passes.

## Risks / Trade-offs

- [Risk] GitCode clone can be slow or unavailable in CI. -> Mitigation: failure is visible and actionable rather than silently skipped.
- [Risk] Oracle C runner may fail to compile against the pinned FlashDB revision. -> Mitigation: CI failure exposes the exact compile error for the next self-healing patch.
- [Risk] CI runtime increases because it clones/builds FlashDB and runs 10000-loop release stress. -> Mitigation: keep the runner small and existing timeout at 60 minutes.

## Migration Plan

1. Update workflow env to configure the C oracle producer.
2. Update CI script so only unconfigured local usage is skipped; configured producer failure fails CI.
3. Run local Rust and OpenSpec checks.
4. Push branch and inspect the new GitHub Actions run.
5. Use any CI compile or runtime error stack for the next precise self-healing patch.

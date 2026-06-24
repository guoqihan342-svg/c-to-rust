# L3 Validation Checklist

Use this checklist before reporting any L3 semantic-equivalence claim.

## Scope

- [ ] Slice id is named and stable.
- [ ] Source project commit is pinned.
- [ ] Rust repo commit is recorded.
- [ ] C source boundary and Rust public API boundary are recorded.
- [ ] Fixture path, fixture hash, and operation count are recorded.
- [ ] Config profile id is recorded.
- [ ] C config header path and hash are recorded.
- [ ] C defines, feature matrix, compile/include profile, Rust Cargo features, Rust feature environment, backend, and toolchain inputs are recorded.
- [ ] Non-goals and accepted differences are written before the pass claim.

## Required Evidence

- [ ] Slice contract exists.
- [ ] Context pack exists.
- [ ] Impact set or equivalent boundary evidence exists.
- [ ] Config profile exists or equivalent version/cache evidence records all required profile fields.
- [ ] C oracle report exists and records generated status from a real C toolchain.
- [ ] Rust replay report exists.
- [ ] C and Rust reports use the same fixture hash.
- [ ] Schema-aware diff exists and passes.
- [ ] Negative diff exists and fails as expected.
- [ ] Rust check or compile/test report exists.
- [ ] Unsafe scan exists.
- [ ] Unsafe ledger exists or the summary links to a ledger-equivalent audit.
- [ ] Performance smoke exists and is marked secondary-only.
- [ ] Summary JSON exists.
- [ ] Version/config manifest or equivalent binding exists.

## Config Profile

- [ ] Profile binds `source_commit`, `repo_commit`, fixture hash, config header hash, C defines, feature matrix, compile command/include paths, Rust Cargo features, Rust feature environment, backend, Cargo lock hash, and toolchain versions.
- [ ] Profile changes invalidate C oracle, Rust replay, schema diff, negative diff, unsafe ledger, performance smoke, cache metadata, and summary evidence.
- [ ] Profile is described as traceability/cache evidence, not as complete macro activation-condition coverage.
- [ ] Async, multithreaded, and runtime-cache semantics remain non-goals unless separate evidence exists.

## Claim Boundary

- [ ] Summary states the named slice and fixture input domain.
- [ ] Summary states behavior fields checked.
- [ ] Summary lists accepted metadata differences.
- [ ] Summary lists forbidden behavior differences.
- [ ] Summary lists known gaps.
- [ ] Summary does not claim full project migration.
- [ ] Summary does not claim byte-for-byte image equivalence unless separately proven.
- [ ] Summary does not claim GC, power-loss, sector layout, capacity pressure, async, thread, or cache semantics unless separately proven.

## Verification

- [ ] C oracle generation command or producer evidence is recorded.
- [ ] Rust replay command is recorded.
- [ ] Diff command is recorded.
- [ ] Negative diff command or mutation is recorded.
- [ ] Rust check/test command is recorded.
- [ ] Unsafe scan command is recorded.
- [ ] OpenSpec validation is recorded when a change is involved.
- [ ] `git diff --check` or equivalent whitespace check is recorded before commit.

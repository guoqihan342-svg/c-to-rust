# L3 Validation Checklist

Use this checklist before reporting any L3 semantic-equivalence claim.

## Scope

- [ ] Slice id is named and stable.
- [ ] Source project commit is pinned.
- [ ] Rust repo commit is recorded.
- [ ] C source boundary and Rust public API boundary are recorded.
- [ ] Fixture path, fixture hash, and operation count are recorded.
- [ ] Non-goals and accepted differences are written before the pass claim.

## Required Evidence

- [ ] Slice contract exists.
- [ ] Context pack exists.
- [ ] Impact set or equivalent boundary evidence exists.
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


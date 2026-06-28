英文镜像见 `checklist.en.md`。

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
- [ ] Pointer dependency graph is recorded for pointer-bearing slices, or marked `not_applicable` with a reason for pure value slices.
- [ ] Alias-sensitive pointer graphs have matching `claim_boundary.alias_gate` in the L3 evidence manifest.
- [ ] Code-test translation manifest path and status are recorded.
- [ ] Non-goals and accepted differences are written before the pass claim.

## Required Evidence

- [ ] Slice contract exists.
- [ ] Context pack exists.
- [ ] Impact set or equivalent boundary evidence exists.
- [ ] Config profile exists or equivalent version/cache evidence records all required profile fields.
- [ ] Pointer dependency graph exists for pointer-bearing slices or records a `not_applicable` reason.
- [ ] Alias gate status is propagated from pointer graph to auto-translation plan, auto manifest, L3 evidence manifest, final verification, and cache metadata when applicable.
- [ ] Code-test translation evidence exists and maps C tests, fixtures, or oracle expectations to Rust test files, test names, cargo commands, coverage categories, negative cases, and known gaps.
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
- [ ] Automatic-translation L3 evidence includes persisted C2Rust baseline manifest, route decision, and validation profile refs.
- [ ] Baseline/route/profile refs are present in the auto manifest, L3 evidence manifest, final verification, and cache metadata.
- [ ] Cache identities for baseline/route/profile match canonical JSON content hashes.
- [ ] Schema-aware diff and negative diff include accepted-evidence refs, required-input status, empty blocked lists, and mutation-detected evidence.

## Config Profile

- [ ] Profile binds `source_commit`, `repo_commit`, fixture hash, config header hash, C defines, feature matrix, compile command/include paths, Rust Cargo features, Rust feature environment, backend, Cargo lock hash, and toolchain versions.
- [ ] Profile changes invalidate C oracle, Rust replay, schema diff, negative diff, unsafe ledger, performance smoke, cache metadata, and summary evidence.
- [ ] Profile is described as traceability/cache evidence, not as complete macro activation-condition coverage.
- [ ] Async, multithreaded, and runtime-cache semantics remain non-goals unless separate evidence exists.

## Pointer Dependency Graph

- [ ] Graph applicability decision covers pointer parameters, pointer returns, pointer fields, buffers, callbacks, opaque handles, globals, manual allocation, and external mutable state.
- [ ] Graph records pointer nodes, dependency edges, ownership/lifetime assumptions, external state, Rust mapping strategy, and known gaps.
- [ ] Graph records read effects, write effects, alias risks, alias contract, and safe boundary preconditions for alias-sensitive read/write slices.
- [ ] Graph changes invalidate ContextPack, PatchPlan, C oracle, Rust replay, schema diff, negative diff, unsafe ledger, performance smoke, cache metadata, and summary evidence.
- [ ] Graph is described as dependency evidence, not complete alias safety proof.
- [ ] 中文检查：L3 claim 可以说 alias 风险已被记录和门禁处理，但不能在没有独立证明时声称 whole-program alias safety。

## Code-Test Translation

- [ ] Manifest maps source fixtures, C tests, or oracle expectations to Rust test files and test names.
- [ ] Generated oracle fixtures are allowed as source mappings when no direct upstream C test name exists.
- [ ] Main-path, error-path, and negative/regression coverage entries are listed.
- [ ] Negative cases link to Rust test names and diff evidence when behavior-diff gates exist.
- [ ] Invalidation keys include source commit, repo commit, fixture hashes, Rust test file hashes, test names, cargo command, accepted differences, profile ids, and schema version.
- [ ] Manifest is described as traceability/cache evidence, not as semantic-equivalence proof.

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
- [ ] Test translation manifest and cargo test commands are recorded.
- [ ] Unsafe scan command is recorded.
- [ ] OpenSpec validation is recorded when a change is involved.
- [ ] `git diff --check` or equivalent whitespace check is recorded before commit.

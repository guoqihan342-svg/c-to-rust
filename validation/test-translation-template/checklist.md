# Code-Test Translation Checklist

Use this checklist before claiming L2 or L3 success for a translated slice.

## Scope

- [ ] `target_id`, `slice_id`, `level`, `source_commit`, and `repo_commit` are recorded.
- [ ] The slice boundary matches the slice contract or L2 slice plan.
- [ ] Source fixtures, C tests, or oracle reports are listed.
- [ ] Rust test files and test function names are listed.
- [ ] Cargo command and Rust test framework are listed.
- [ ] The manifest status is `recorded`, or `not_applicable` with a concrete reason.

## Mapping

- [ ] Each source fixture, C test, or oracle expectation maps to at least one Rust test or replay command.
- [ ] A generated oracle fixture is accepted as a source mapping when no upstream C test name exists.
- [ ] Main-path behavior is listed explicitly.
- [ ] Error-path behavior is listed explicitly, or a known gap explains why it is outside the slice.
- [ ] Negative/regression cases are listed when diff gates exist.
- [ ] Known gaps do not contradict the success claim.

## Evidence Links

- [ ] C oracle or golden fixture evidence is linked.
- [ ] Rust replay or Rust test report is linked.
- [ ] Schema-aware diff is linked when the slice is L3.
- [ ] Negative diff or mutation evidence is linked when the slice has behavior-diff gates.
- [ ] Unsafe evidence is linked.
- [ ] Pointer dependency graph evidence is linked or marked `not_applicable` elsewhere for pure value slices.
- [ ] Config/profile evidence is linked for L3 slices.

## Invalidation

- [ ] Fixture hashes are recorded.
- [ ] Rust test file hashes or equivalent version identifiers are recorded.
- [ ] Cargo command, feature flags, and profile-affecting inputs are recorded.
- [ ] Changes to source commit, repo commit, fixture hash, Rust test file hash, test names, cargo command, accepted differences, profile ids, or schema version invalidate affected evidence.

中文：如果上述任意输入漂移，相关 ContextPack、PatchPlan、C oracle、Rust replay、diff、unsafe、performance、cache 和 summary 证据必须重新生成或显式标记失效。


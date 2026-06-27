# Validation Gates

中文：所有复杂 C 项目必须按层级推进。不能用低层级证据冒充高层级迁移成功。

English: each complex C project moves through layered gates. Lower-level evidence must never be reported as higher-level migration success.

## L0: Catalog and Remote Probe

Purpose: prove the target is well described and reachable without cloning large repositories.

Pass criteria:

- `projects.json` is valid JSON.
- At least 12 unique targets exist.
- Required fields are present for every target.
- Optional `-ProbeRemote` records `git ls-remote --symref <repo> HEAD`.
- Evidence report records `level:"L0"`.

Evidence:

- `validation/evidence/catalog-validation.json`
- `validation/evidence/catalog-remote-probe.json`

Failure handling:

- Missing required metadata fails the script.
- Remote probe failures are recorded per target and make the probe run fail.

## L1: Native C Build and Test Smoke

Purpose: prove a pinned upstream C checkout can build and run a small native smoke test in an external workspace.

Pass criteria:

- Commit is pinned.
- Build dependencies and versions are recorded.
- Environment profile path and hash are recorded when the run targets the competition/evaluation host, for example `validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json`.
- Native C build command exits 0.
- Native smoke test command exits 0.
- Evidence includes stdout/stderr paths, command exit codes, tool versions, and elapsed time.

Evidence:

- `validation/evidence/<target>/l1-native-build.json`
- External clone path and commit hash.

## L2: Bounded Migration Slice

Purpose: prove the agent can migrate a narrow, named C slice to compiling Rust without breaking the rest of the project context.

Pass criteria:

- Slice scope is declared before migration.
- C function/file boundaries and callers/callees are recorded.
- Pointer dependency graph evidence is recorded before translation when the slice has C pointer parameters, pointer returns, struct pointer fields, buffers, opaque handles, callbacks, manual allocation, external mutable state, or alias-sensitive state. Pure value slices record `not_applicable` with a reason.
- Code-test translation evidence maps C tests, fixtures, or oracle expectations to Rust test files, Rust test names, cargo commands, coverage categories, negative cases, evidence links, and known gaps. A generated oracle fixture can serve as the source mapping when no direct upstream C test name exists.
- Rust translation compiles.
- First-party unsafe usage is counted and recorded in an unsafe ledger, even when the count is zero.
- Every accepted L2 slice has a negative diff proving the diff gate catches an intentional mismatch.
- Compile self-healing records all rustc errors and patches.

Evidence:

- `validation/evidence/<target>/l2-slice-plan.json`
- `validation/evidence/<target>/l2-<slice>-pointer-graph.json` or `not_applicable` pointer graph evidence with a reason
- `validation/evidence/<target>/l2-<slice>-test-translation.json` or `not_applicable` test translation evidence with a reason
- `validation/evidence/<target>/l2-rust-check.json`
- C oracle fixture and Rust replay report for each slice.
- Schema-aware diff report for each slice.
- Unsafe scan plus unsafe ledger, even when first-party unsafe count is zero.
- A negative diff report for every accepted L2 slice proving the diff gate catches an intentional mismatch.
- L2 summary references unsafe ledger and negative diff status.
- Patch log and reporting boundary for the named slice only.

## L3: Semantic and Performance Evidence

Purpose: prove behavior-level equivalence for the migrated slice.

Pass criteria:

- C oracle or golden fixture is generated from the same input sequence.
- Pointer dependency graph evidence is recorded for pointer-bearing slices or explicitly marked `not_applicable` for pure value slices.
- Config profile records the C config header hash, macro/feature matrix, compile/include profile, Rust Cargo features, Rust feature environment, backend profile, fixture hash, toolchain versions, environment profile path/hash when applicable, and cache invalidation keys.
- Code-test translation evidence maps the source fixtures, C tests, or oracle expectations to Rust tests, main/error path coverage, negative cases, evidence links, and cache invalidation keys.
- Automatic migration evidence records C2Rust baseline availability, route decision, and validation profile as first-class evidence. C2Rust output is candidate context only and cannot replace the original C oracle, Rust replay, diff, unsafe, or final-verification gates.
- Legacy accepted auto-translation fixtures that are validated by the current semantic-pass path also persist these baseline/route/profile refs and schema-aware diff / negative-diff gate metadata. Compatibility for older optional fields does not permit missing semantic-pass refs.
- Rust output is compared against C/golden output by schema-aware diff.
- Negative regression counterexample fails as expected.
- Performance smoke records timing or operation counters without replacing correctness gates.

Evidence:

- `validation/evidence/<target>/l3-c-oracle.json`
- `validation/evidence/<target>/l3-rust-report.json`
- `validation/evidence/<target>/l3-diff.json`
- `validation/evidence/<target>/l3-performance-smoke.json`
- `validation/evidence/<target>/l3-config-profile.json` or equivalent version/cache profile evidence
- `validation/evidence/<target>/l3-<slice>-pointer-graph.json` or `not_applicable` pointer graph evidence with a reason
- `validation/evidence/<target>/l3-<slice>-test-translation.json` or equivalent code-test translation evidence
- Slice-specific artifact names and required statuses may be declared through `validation/l3-template/evidence-manifest.json`.

Config profile is a traceability and invalidation gate, not a full macro solver. A profile change invalidates affected C oracle, Rust replay, diff, unsafe, performance, cache, and summary evidence unless those artifacts are regenerated or explicitly invalidated.

中文：config profile 是追溯与缓存失效门禁，不是完整宏求解器。profile 变化时，受影响的 C oracle、Rust replay、diff、unsafe、performance、cache 和 summary 证据必须重新生成或显式失效。

Competition environment profile is a toolchain and mirror provenance gate. A change to `validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json`, or a run performed under a different host/toolchain profile, invalidates build, oracle, replay, cache, performance, and summary claims unless those artifacts are regenerated or explicitly marked as non-competition evidence.

Pointer dependency graph evidence is a context and risk-boundary gate, not a whole-program alias proof. Graph changes invalidate affected ContextPack, PatchPlan, C oracle, Rust replay, diff, unsafe, performance, cache, and summary evidence unless regenerated or explicitly invalidated.

Code-test translation evidence is a traceability and invalidation gate, not a semantic-equivalence proof. It complements C oracle, Rust replay, schema diff, negative diff, unsafe, pointer, config, and final verification evidence; it never replaces them.

C2Rust baseline evidence is a traceability, cross-check, and candidate-context gate, not correctness evidence. Generated, skipped, or blocked baseline status must be recorded, and semantic acceptance still requires the selected validation profile to pass without skipped required gates.

中文：pointer dependency graph 是上下文与风险边界门禁，不是全程序 alias 证明。graph 变化时，受影响的 ContextPack、PatchPlan、C oracle、Rust replay、diff、unsafe、performance、cache 和 summary 证据必须重新生成或显式失效。

## Full Regression Evidence Gates

Purpose: prove a full-regression round consumes the evidence it depends on, not just the compiler and unit-test commands.

Pass criteria:

- L2 reports are regenerated before L2 evidence is validated.
- `validate_l2_evidence_summary.py` passes and confirms each accepted L2 slice has Rust report, positive diff, negative diff, unsafe scan, unsafe ledger, and test translation evidence.
- `validate_test_translation_coverage.py` passes and confirms recorded test translation evidence has main-path coverage and negative-case evidence.
- FlashDB committed fixture replay passes positive diff.
- `flashdb_fixture_negative_diff.py` mutates committed fixture expected behavior and confirms `diff-report` fails with a mismatch path.
- `cargo run -- unsafe-scan --report <path>` writes a machine-readable unsafe report with category counts and zero first-party non-test unsafe findings.
- `validate_flashdb_version_binding.py` consumes `version-manifest` and checks Cargo package/version, schema/tool versions, source commit, feature matrix, and cache-key inputs.
- `validate_flashdb_l3_evidence.py` validates consumable FlashDB L3 packages with final verification and negative diff evidence; older summaries without those entry points are reported as `legacy_incomplete` and cannot be used as full-regression manifest claims.
- FlashDB L3 package validation reads positive diff and final verification report content, rejects failed or mismatched evidence, and verifies summary-declared evidence `sha256` values when present.
- When `scripts/run-full-regression.ps1 -RequireCleanEvidence` is used, `evidence-cleanliness-check` verifies that tracked files under `validation/evidence/**` do not differ from `HEAD` and that no untracked files exist under `validation/evidence/**`.
- OpenSpec validation and `git diff --check` still run after the evidence gates.

Evidence:

- Per-round reports under `target/full-regression/<run-id>/round-xxxxx/`.
- `l2-evidence-summary.json`
- `test-translation-coverage.json`
- `flashdb-rust-fixture-negative-diff.json`
- `flashdb-unsafe-scan.json`
- `flashdb-version-binding.json`
- `flashdb-l3-evidence.json`

Boundary:

- Full regression does not prove production-data equivalence unless real or de-identified production fixtures are supplied to replay/diff.
- Full regression does not claim llvm-cov percentage, symbolic path exhaustiveness, or full FlashDB C project migration.
- Performance smoke remains secondary evidence and never replaces C/Rust behavior diff or negative controls.
- Evidence cleanliness is an explicit reproducibility gate for committed evidence. It is not enabled by default during local development, it treats staged tracked evidence changes as not-yet-committed drift, and it does not inspect per-round reports under `target/full-regression/**`.

## Reporting Rules

- L0 passed: catalog target is eligible for deeper validation.
- L1 passed: native C baseline is reproducible.
- L2 passed: a bounded Rust migration slice compiles and has required L2 safety, diff-gate, and code-test translation evidence.
- L3 passed: the bounded slice has behavior evidence plus synchronized code-test translation evidence.

Only L3 can support a limited semantic-equivalence claim, and only for the named slice and pinned commit.

Automatic translation capability claims require more than L1 target success or a hand-authored `c_source` string. A slice only counts as real-source automatic translation evidence when the slice spec is generated from real C source files with source span, source hash, build profile provenance, and completed L3 evidence for the named function.

中文：catalog gate 的 `level:"L0"` 与 auto-translation `route_decision.level="L0"` 是两种不同证据。后者只表示 deterministic zero-token candidate routing，不是 catalog L0 pass、不是 L1/L2/L3 evidence，也不证明语义等价；C oracle、Rust replay、schema diff、negative diff、unsafe ledger 和 final verification 仍是 semantic acceptance 的来源。

English: catalog `level:"L0"` and auto-translation `route_decision.level="L0"` are different evidence concepts. The latter means deterministic zero-token candidate routing only; it is not catalog L0 pass, not L1/L2/L3 evidence, and not proof of semantic equivalence. C oracle, Rust replay, schema diff, negative diff, unsafe ledger, and final verification remain the sources of semantic acceptance.

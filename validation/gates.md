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
- Rust translation compiles.
- First-party unsafe usage is counted and recorded in an unsafe ledger, even when the count is zero.
- At least one L2 negative diff proves the diff gate catches an intentional mismatch.
- Compile self-healing records all rustc errors and patches.

Evidence:

- `validation/evidence/<target>/l2-slice-plan.json`
- `validation/evidence/<target>/l2-rust-check.json`
- C oracle fixture and Rust replay report for each slice.
- Schema-aware diff report for each slice.
- Unsafe scan plus unsafe ledger, even when first-party unsafe count is zero.
- At least one L2 negative diff report proving the diff gate catches an intentional mismatch.
- L2 summary references unsafe ledger and negative diff status.
- Patch log and reporting boundary for the named slice only.

## L3: Semantic and Performance Evidence

Purpose: prove behavior-level equivalence for the migrated slice.

Pass criteria:

- C oracle or golden fixture is generated from the same input sequence.
- Rust output is compared against C/golden output by schema-aware diff.
- Negative regression counterexample fails as expected.
- Performance smoke records timing or operation counters without replacing correctness gates.

Evidence:

- `validation/evidence/<target>/l3-c-oracle.json`
- `validation/evidence/<target>/l3-rust-report.json`
- `validation/evidence/<target>/l3-diff.json`
- `validation/evidence/<target>/l3-performance-smoke.json`
- Slice-specific artifact names and required statuses may be declared through `validation/l3-template/evidence-manifest.json`.

## Reporting Rules

- L0 passed: catalog target is eligible for deeper validation.
- L1 passed: native C baseline is reproducible.
- L2 passed: a bounded Rust migration slice compiles and has required L2 safety/diff-gate evidence.
- L3 passed: the bounded slice has behavior evidence.

Only L3 can support a limited semantic-equivalence claim, and only for the named slice and pinned commit.

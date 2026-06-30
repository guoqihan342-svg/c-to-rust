# Judge Demo Entrypoint

Chinese source: `judge-demo.md`.

Primary judge path: real FlashDB `real-fdb-calc-crc32`.
Fallback path: repo-local `demo/store-add-one`.

The primary path is the current scoring story for core translation capability plus harness architecture: original unsafe Rust, final safe Rust, accepted patch, oracle evidence, unsafe before/after, five-stage harness contract, and milestone report.

## Real FlashDB One-Command Path

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
```

Key FlashDB artifacts:

- `target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/workflow-metrics.json`
- baseline unsafe Rust: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-baseline-unsafe.rs`
- final safe Rust: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-final-safe.rs`
- accepted safety patch: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-accepted-safety.patch`
- safety step log: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-safety-step-log.jsonl`
- before/after manifest: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-translation-before-after.json`

The bound real slice is `sources/FlashDB/src/fdb_utils.c#fdb_calc_crc32` at commit `f9d0421315c564fb890a1b14eee77b290e0d7bbe`. The core per-unit unsafe number is `real-fdb-calc-crc32`: baseline unsafe count `2`, final unsafe count `0`, `reduced_by=2`.

Boundary: the baseline is a reviewed unsafe Rust baseline derived from the real C slice signature. C2Rust baseline output remains skipped, so do not claim that this baseline came from real C2Rust output. `generated_draft_semantic_pass=false`, and this exhibit still does not increase `translation_coverage_numerator`.

## Fallback Demo One-Command Path

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

Fallback demo artifacts:

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-demo-before-after-exhibit/summary/workflow-metrics.json`
- baseline unsafe Rust: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-baseline-unsafe.rs`
- final safe Rust: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-final-safe.rs`
- accepted safety patch: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-accepted-safety.patch`
- unsafe scan: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-before-after-unsafe-scan.json`
- safety step log: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-safety-step-log.jsonl`
- before/after manifest: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json`

The fallback demo shows unsafe 3 -> 0 for `demo/store-add-one`.

## Claim Boundary

- `before-after-exhibit.json` is the judge-facing exhibit entrypoint. It proves artifact binding, unsafe delta, and the harness contract; it does not replace `competition-run-summary.json`, `workflow-metrics.json`, or the evidence validator.
- `translation_coverage_numerator` does not increase because of these exhibits; the coverage numerator may only count translator-generated candidates that pass the corresponding gate for a named slice.
- All public paths must remain repo-relative. Do not put local absolute paths or WSL host paths into public claims.

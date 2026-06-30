# Judge Demo Entrypoint

Chinese source: `judge-demo.md`.

This is the shortest public demo path for the current branch. It targets the two scoring axes: core translation capability and harness architecture. The repo-local demo slice shows one evidence chain: original unsafe Rust, final safe Rust, accepted patch, oracle evidence, unsafe before/after, five-stage harness contract, and milestone report.

## One-Command Demo Path

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

After running the profile, the key exhibit artifacts are:

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-demo-before-after-exhibit/summary/workflow-metrics.json`

## Before/After Evidence

The current demo binds these translation-quality artifacts:

- baseline unsafe Rust: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-baseline-unsafe.rs`
- final safe Rust: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-final-safe.rs`
- accepted safety patch: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-accepted-safety.patch`
- unsafe scan: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-before-after-unsafe-scan.json`
- safety step log: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-safety-step-log.jsonl`
- before/after manifest: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json`

The core per-unit `unsafe_reduction` numbers are: baseline unsafe count `3`, final unsafe count `0`, and `reduced_by=3`. The semantic boundary is bound by the C oracle, Rust replay, and final verification. The harness only connects the evidence into a reproducible planner -> worker -> verifier -> repairer -> reporter contract.

## Claim Boundary

- `generated_draft_semantic_pass=false`: this demo presents accepted-evidence-authoritative before/after safety-refactoring evidence. It does not package the generated draft itself as semantic pass.
- `translation_coverage_numerator` does not increase because of this demo; the coverage numerator may only count translator-generated candidates that pass the corresponding gate for a named slice.
- `before-after-exhibit.json` is the judge-facing exhibit entrypoint. It proves artifact binding, unsafe delta, and the harness contract; it does not replace `competition-run-summary.json`, `workflow-metrics.json`, or the evidence validator.
- All paths must remain repo-relative; do not put local absolute paths or WSL host paths into public claims.

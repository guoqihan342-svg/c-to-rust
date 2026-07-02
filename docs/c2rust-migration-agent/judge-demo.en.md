# Judge Demo Entrypoint

Chinese source: `judge-demo.md`.

Primary judge path: real FlashDB `real-fdb-calc-crc32`.
Fallback path: repo-local `demo/store-add-one`.

The primary path is the current scoring story for core translation capability plus harness architecture: original unsafe Rust, final safe Rust, accepted patch, oracle evidence, unsafe before/after, five-stage harness contract, and milestone report.

## Real FlashDB One-Command Path

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
```

Audit-expanded form:

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python3 -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
```

Key FlashDB artifacts:

- `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/judge-evidence-index.json`
- H5 context pack: `target/competition-out-flashdb-before-after-exhibit/harness/context-pack.json`
- agent index: `target/competition-out-flashdb-before-after-exhibit/harness/agent-index.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/workflow-metrics.json`
- baseline unsafe Rust: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-baseline-unsafe.rs`
- final safe Rust: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-final-safe.rs`
- accepted safety patch: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-accepted-safety.patch`
- safety step log: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-safety-step-log.jsonl`
- before/after manifest: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-translation-before-after.json`
- H4 run manifest: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-h4-baseline-repair-run.json`, a tracked record for `harness-h4-flashdb-context-index-20260701` with reproduction commands, target run artifact hashes, the attempt 1/2 repair trace, and the `translation_coverage_numerator=0` boundary.

The bound real slice is `sources/FlashDB/src/fdb_utils.c#fdb_calc_crc32` at commit `f9d0421315c564fb890a1b14eee77b290e0d7bbe`. The core per-unit unsafe number is `real-fdb-calc-crc32`: baseline unsafe count `2`, final unsafe count `0`, `reduced_by=2`.

Boundary: the before/after exhibit baseline is still a reviewed unsafe Rust baseline derived from the real C slice signature. The C2Rust baseline now has generated + compile-only + direct replay observable-passed evidence, but it remains `candidate_context_only` / `semantic_pass=false`; do not claim that the before/after baseline came from a verified C2Rust output. `generated_draft_semantic_pass=false`, and this exhibit still does not increase `translation_coverage_numerator`.

Harness self-repair exhibit: the `flashdb-fdb-utils-before-after` profile now declares `attempt_evidence_policy.mode=baseline_repair_gate`. Worker attempt 1 writes a failed baseline unsafe gate summary with root cause `unsafe_baseline_requires_repair`; attempt 2 must carry the repair hint before revalidating accepted safe evidence. Both `harness/context-pack.json` and `harness/agent-index.json` index this policy and the two-attempt timeline.

## Fallback Demo One-Command Path

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
```

Audit-expanded form:

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python3 -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

Fallback demo artifacts:

- `target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/judge-evidence-index.json`
- H5 context pack: `target/competition-out-demo-before-after-exhibit/harness/context-pack.json`
- agent index: `target/competition-out-demo-before-after-exhibit/harness/agent-index.json`
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

- `judge-demo-report.json` is the one-command aggregate report. It binds the paths and sha256 values for `competition-run-summary.json`, `workflow-metrics.json`, `before-after-exhibit.json`, `milestone-release-report.json`, and the copied `milestone-review-checklist.json`.
- `harness/judge-evidence-index.json` is the same-shape judge evidence index. It binds `judge-demo-report.json`, summaries, workflow metrics, before/after exhibit, milestone, context pack, agent index, run/merge/worker plan paths and sha256 values; it is not a semantic gate and it does not self-reference.
- The review checklist / review gate is release-readiness input and audit evidence only. It is not a semantic acceptance gate and does not increase `translation_coverage_numerator`.
- `judge-demo-report.json.repair_summary` aggregates repair/retry/rollback exhibit fields, including the repair round cap, auto recovery, root cause counts, repair history, and rollback ids. It only comes from bound workflow metrics / before-after exhibit data and does not replace the validator or oracle.
- `before-after-exhibit.json` is the judge-facing exhibit entrypoint. It proves artifact binding, unsafe delta, and the harness contract; it does not replace `competition-run-summary.json`, `workflow-metrics.json`, or the evidence validator.
- `harness/context-pack.json` and `harness/agent-index.json` are `run-batch-profile` generated H5 harness audit indexes and multi-agent continuation entrypoints. They expose the planner/worker/merge/report topology and worker assignments; they do not replace the summary, validator, or oracle, and they do not expand the semantic pass claim.
- `translation_coverage_numerator` does not increase because of these exhibits; the coverage numerator may only count translator-generated candidates that pass the corresponding gate for a named slice.
- All public paths must remain repo-relative. Do not put local absolute paths or WSL host paths into public claims.

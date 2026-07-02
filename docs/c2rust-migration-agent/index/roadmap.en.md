# English Mirror: Roadmap

Chinese original: `roadmap.md`.

This file is the English mirror for `docs/c2rust-migration-agent/index/roadmap.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the categorized document index for the migration-agent documentation set. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# 覆盖与路线`
- `## 评委 Demo / Milestone`

## Judge Demo / Milestone

The current public before/after demo entrypoint is `../judge-demo.md`.
The machine-readable judge entrypoint directory is `../../../config/competition-env/judge-entrypoints/flashdb-harness.json`; it binds the competition environment smoke, FlashDB before/after demo, deterministic explicit multi-worker evaluate profile, OpenCode explicit multi-worker evaluate profile, expected artifacts including `worker_plan`, tracked manifests, and claim boundaries in one place.

Full judge public packet entrypoint:

```bash
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
```

After success, the command writes `judge-milestone-bundle.json`, `milestone-release-notes.md`, and `public-release-packet.json` in the same summary directory. The bundle is the machine-readable external review index, the Markdown notes render the judge packet index for humans, and the JSON public release packet hash-binds the run report, readiness report, bundle, release notes, and config archive before `validate_public_release_packet` checks schema, hashes, claim boundary, local-path hygiene, packet-to-bundle consistency, and release-notes consistency against the bundle rendering; none of these artifacts is a semantic gate or increases `translation_coverage_numerator`.

Focused smoke/triage entrypoint example:

```bash
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id competition_environment_smoke --out target/h7-judge-smoke/summary/judge-entrypoints-run-report.json
```

After a successful focused run, the runner writes `selected-entrypoints-validation-config.json` next to the report, and post-run local-artifact deep validation checks only the selected entrypoints while narrowing `test_contract.required_entrypoint_ids`. This is for smoke/triage, not a full public packet; external publication should use the full entrypoint without `--entrypoint-id`.

With `--require-local-artifacts`, `validate_judge_entrypoints` also deep-validates non-smoke `competition_summary` artifacts through `validate_competition_run_summary.py`, including workflow metrics, before/after refs, repair history, unsafe accounting, final-gate rules, and slice counts.

The same public packet now folds C2Rust baseline manifest status into route-governance and the milestone scorecard: `raw_c2rust.c2rust_baseline_rollup` deduplicates by evidence root, shows manifest/source/compile-pass counts, and still keeps `semantic_gate=false` plus `translation_coverage_numerator=0`.

Primary real FlashDB run:

```bash
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
```

Audit-expanded form:

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
```

Key artifacts:

- `target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/context-pack.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/agent-index.json`

Boundary: `milestone-review-checklist.json` / the review gate is audit input for release readiness and public claim boundaries only. It is not a semantic acceptance gate and does not increase `translation_coverage_numerator`.

Current harness-first development entrypoint:

```bash
python -B -m validation.tools.opencode_agent_harness evaluate --run-id run-evaluate --target-id flashdb --source-repo-root <repo-relative-source-root> --source-file <source.c> --source-commit <commit> --out-root target/competition-out-evaluate --proof-class local-simulation --max-workers 4
```

Profile form of the same one-command entrypoint:

```bash
python -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json --run-id harness-flashdb-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701
```

This path reuses the full batch-profile pipeline and additionally emits a `harness/evaluate-report.json` wrapper plus `harness/judge-evidence-index.json`. These only index verified batch artifacts, summary validation, and context/index entrypoints; they are not a new semantic acceptance gate.

OpenCode explicit multi-worker judge entrypoint:

```bash
python -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json --run-id harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-opencode-explicit-workers-evaluate-profile-20260701
```

This path additionally binds OpenCode preflight, `opencode_agent_runtime`, worker handoff/session/log evidence, `worker_plan`, `context-pack.json`, `agent-index.json`, and `judge-evidence-index.json`; `validate_judge_entrypoints --require-local-artifacts` checks the runtime contract and sha256 bindings. Boundary: OpenCode chat/session output is not semantic evidence and is not a new semantic gate.

This entrypoint emits `harness/evaluate-report.json`, `harness/context-pack.json`, `harness/agent-index.json`, `harness/resume-manifest.json`, and the SQLite `context_packs` index for judge audits and later OpenCode multi-agent continuation; `context_management_contract` / `agent_coordination_contract` make the plan -> worker fan-out -> verify/merge -> repair loop -> report roles, resume protocol, and `chat_output_is_evidence=false` boundary machine-readable. `resume-manifest.json` is a current-state resume index that binds the context/agent hashes, SQLite ledger, worker summaries, and repair hints, but it is not a semantic gate and does not increase `translation_coverage_numerator`.

If OpenCode fails with `database is locked` before issuing the first shell command, the worker records bounded startup retries as `opencode_process_retries`. The retry is runtime stabilization only; contract verification and summary validation still decide whether the worker can be accepted into the merge.

Fallback repo-local demo:

```bash
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
```

Audit-expanded form:

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

Fallback artifacts:

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`

Boundary: the real FlashDB exhibit binds accepted-evidence before/after artifacts for `real-fdb-calc-crc32` and unsafe 2 -> 0. `judge-demo-report.json.repair_summary` only aggregates repair/retry/rollback fields from bound workflow metrics / before-after exhibit data and does not replace the validator or oracle. The C2Rust baseline now has generated + compile-only + direct replay observable-passed evidence, but it remains `candidate_context_only` / `semantic_pass=false`; the exhibit does not increase `translation_coverage_numerator`.

## Maintenance Notes

- Keep filenames paired as `roadmap.md` and `roadmap.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `roadmap.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

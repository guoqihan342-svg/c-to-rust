# English Mirror: Roadmap

Chinese original: `roadmap.md`.

This file is the English mirror for `docs/c2rust-migration-agent/index/roadmap.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the categorized document index for the migration-agent documentation set. It is intentionally concise for older plans, templates, and Superpowers records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# 覆盖与路线`
- `## A19b4c2 检索前沿`
- `## 评委 Demo / Milestone`

## A19b4c2 Retrieval Frontier

- [x] **A19b4c2a: model context-retrieval-not-ready as a recoverable scheduling state, not a terminal semantic-ledger result.** The portfolio explicitly lists `pending_retrieval_groups` while retaining hash-bound assignments. The scheduler defers these workers with `context_retrieval_pending`, so they receive no leases and trigger no model invocations. A controller test verifies zero attempts and zero leases; the finite regression is 527/527 on both Windows and WSL. This item proves only pending classification, binding retention, and the zero-lease/zero-model boundary; it does not claim that pending can recover to `ready`, establish a semantic gate, or increase the translator numerator.
- [x] **A19b4c2b: implement a host-owned, content-bound single-SCC refresh/override.** The host reopens the complete CAS dependency chain for the portfolio, base/new catalogs, selection receipt, pages/group, refresh input, and overlay before a private permit moves the SCC from `pending_retrieval` to `ready`. Dispatch, request, and prelaunch reopen the overlay again, and any drift fails closed before an attempt or provider launch.
- [x] **A19b4c2c: recompute the next retrieval frontier after every wave.** The host derives a wave input and per-SCC selection directives from the portfolio-bound DAG, prior-wave last-good state, explicit failure evidence, and expansion queries. Whole-wave invalidation is one SQLite transaction; per-SCC refresh is idempotently resumable from the same CAS inputs after interruption. Legacy refresh, cross-SCC fact injection, stale/future query epochs, and caller-owned identity fields are rejected. The production entrypoint is `prepare-next-context-frontier-wave`; it remains `semantic_gate=false` with `translation_coverage_numerator=0`.
- [x] **A19b4c2d: keep only a hash-bound portfolio summary in the root plan.** `project-migration-plan.json` no longer duplicates all assignments, ledger units, and context. Dispatch streams path/size/SHA verification on one file handle, requires canonical UTF-8 JSON, and checks run/status/DAG/portfolio-plan identities before immutable-ledger verification. Full CIndex, ContextPages, and portfolio artifacts still need sharding, so the parent remains unchecked.

## Judge Demo / Milestone

The current public before/after demo entrypoint is `../judge-demo.md`.
The machine-readable judge entrypoint directory is `../../../config/competition-env/judge-entrypoints/flashdb-harness.json`; it binds the competition environment smoke, FlashDB before/after demo, deterministic explicit multi-worker evaluate profile, OpenCode explicit multi-worker evaluate profile, expected artifacts including `worker_plan`, tracked manifests, and claim boundaries in one place.

Full judge public packet entrypoint:

```bash
python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
```

After success, the command writes `judge-milestone-bundle.json`, `milestone-release-notes.md`, and `public-release-packet.json` in the same summary directory. The bundle is the machine-readable external review index, the Markdown notes render the judge packet index for humans, and the JSON public release packet hash-binds the run report, readiness report, bundle, release notes, and config archive before `validate_public_release_packet` checks schema, hashes, claim boundary, local-path hygiene, packet-to-bundle consistency, and release-notes consistency against the bundle rendering; none of these artifacts is a semantic gate or increases `translation_coverage_numerator`.

The runner applies a finite 36000-second default timeout to each entrypoint command, overrideable with `--timeout-seconds`; timeouts are recorded in the run report as `entrypoint.timeout_policy`, `root_cause_key=process_timeout`, and `exit_code=124`, then fail closed.

Focused smoke/triage entrypoint example:

```bash
python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id competition_environment_smoke --out target/h7-judge-smoke/summary/judge-entrypoints-run-report.json
```

After a successful focused run, the runner writes `selected-entrypoints-validation-config.json` next to the report, and post-run local-artifact deep validation checks only the selected entrypoints while narrowing `test_contract.required_entrypoint_ids`. This is for smoke/triage, not a full public packet; external publication should use the full entrypoint without `--entrypoint-id`.

With `--require-local-artifacts`, `validate_judge_entrypoints` also deep-validates non-smoke `competition_summary` artifacts through `validate_competition_run_summary.py`, including workflow metrics, before/after refs, repair history, unsafe accounting, final-gate rules, and slice counts.

The same public packet now folds C2Rust baseline manifest status into route-governance and the milestone scorecard: `raw_c2rust.c2rust_baseline_rollup` deduplicates by evidence root, shows manifest/source/compile-pass counts, and still keeps raw C2Rust at `semantic_gate=false` plus `translation_coverage_numerator=0`; typed-IR generated-draft acceptance is counted separately, and the coverage matrix now derives `translator_generated_semantic_pass_count=24`, including `real-fdb-calc-crc32`, `real-fdb-blob-make`, `real-fdb-is-str`, `real-fdb-kv-del`, `real-fdb-kv-set`, `real-fdb-kv-to-blob`, `real-fdb-new-kv-alloc-compare`, `real-fdb-tsl-to-blob`, `zlib-ng/adler32-step`, and a set of demo exact typed-IR drafts.

Primary real FlashDB run:

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
```

Audit-expanded form:

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
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
python3 -B -m validation.tools.opencode_agent_harness evaluate --run-id run-evaluate --target-id flashdb --source-repo-root <repo-relative-source-root> --source-file <source.c> --source-commit <commit> --out-root target/competition-out-evaluate --proof-class local-simulation --max-workers 4
```

Profile form of the same one-command entrypoint:

```bash
python3 -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json --run-id harness-flashdb-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701
```

This path reuses the full batch-profile pipeline and additionally emits a `harness/evaluate-report.json` wrapper plus `harness/judge-evidence-index.json`. These only index verified batch artifacts, summary validation, and context/index entrypoints; they are not a new semantic acceptance gate.

OpenCode explicit multi-worker judge entrypoint:

```bash
python3 -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json --run-id harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-opencode-explicit-workers-evaluate-profile-20260701
```

This path additionally binds OpenCode preflight, `opencode_agent_runtime`, worker handoff/session/log evidence, `worker_plan`, `context-pack.json`, `agent-index.json`, and `judge-evidence-index.json`; `validate_judge_entrypoints --require-local-artifacts` checks the runtime contract and sha256 bindings. Boundary: OpenCode chat/session output is not semantic evidence and is not a new semantic gate.

This entrypoint emits `harness/evaluate-report.json`, `harness/context-pack.json`, `harness/agent-index.json`, `harness/resume-manifest.json`, and the SQLite `context_packs` index for judge audits and later OpenCode multi-agent continuation; `context_management_contract` / `agent_coordination_contract` make the plan -> worker fan-out -> verify/merge -> repair loop -> report roles, resume protocol, and `chat_output_is_evidence=false` boundary machine-readable. `resume-manifest.json` is a current-state resume index that binds the context/agent hashes, SQLite ledger, worker summaries, and repair hints, but it is not a semantic gate and does not increase `translation_coverage_numerator`.

If OpenCode fails with `database is locked` before issuing the first shell command, the worker records bounded startup retries as `opencode_process_retries`. The retry is runtime stabilization only; contract verification and summary validation still decide whether the worker can be accepted into the merge.

Fallback repo-local demo:

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
```

Audit-expanded form:

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

Fallback artifacts:

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`

Boundary: the real FlashDB exhibit binds accepted-evidence before/after artifacts for `real-fdb-calc-crc32` and unsafe 2 -> 0. `judge-demo-report.json.repair_summary` only aggregates repair/retry/rollback fields from bound workflow metrics / before-after exhibit data and does not replace the validator or oracle. The C2Rust baseline now has generated + compile-only + direct replay observable-passed evidence, but it remains `candidate_context_only` / `semantic_pass=false`; typed-IR generated Rust drafts count only when their exact drafts have `generated_draft_acceptance.status=passed`, and the current translator-generated numerator is 22.

## Maintenance Notes

- Keep filenames paired as `roadmap.md` and `roadmap.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `roadmap.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, Superpowers tasks, and validation checklists are scoped artifacts only.

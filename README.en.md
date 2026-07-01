# English Mirror:  README

Chinese original: `README.md`.

This file is the English mirror for `README.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the repository overview and quick entry point. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# C-to-Rust Progressive Migration Pipeline`
- `## 愿景`
- `## 架构概览`
- `## L0-L4 验证分层`
- `## 当前状态`
- `## 核心目录`
- `## 待办来源`
- `## OpenCode 比赛单次交互`
- `## 快速命令`
- `# 运行翻译器测试（默认 feature）`
- `# 运行翻译器测试（含 typed IR + clang frontend）`
- `# 运行 auto migration（以 FlashDB crc32 为例）`
- `# 验证自动翻译证据`
- `# 语义通过验证`
- `# 全量回归`
- `## 设计原则`

## Current OpenCode Competition Summary

The Chinese README now treats the 600-minute figure as an optional external evaluation budget, not as an optimization target. The competition path prioritizes accuracy and complete evidence, may process independent slices with parallel agents or batch workers, and requires isolated worker outputs plus common validator/final-verification acceptance.

The current typed-IR route includes local fixed-size integer arrays and readonly `static const` fixed-size integer global array index reads, including the restricted clang `array_filler` sparse initializer subset.

Current FlashDB accepted evidence includes both `real-fdb-calc-crc32` and `real-fdb-blob-make` through the L4 accepted-evidence-authoritative path. Their generated Rust drafts remain candidates with `generated_draft_semantic_pass=false`. `fdb_kv_set` still has L4 refused/blocked evidence because its external callee semantics are not closed by verified shims, models, or oracle evidence.

The current documentation-update branch is `codex/agent-harness-flashdb-mvp`; the baseline development branch remains `codex/flashdb-rust-skeleton`.

## Current Harness MVP Status

- Current branch: `codex/agent-harness-flashdb-mvp`.
- The OpenCode harness now has a minimal executor: `python -m validation.tools.opencode_agent_harness run-worker --mode deterministic` invokes the repo-local `scripts/c2rust-migrator.py --phase migrate --input ...` path and records the worker summary into the SQLite ledger when present.
- The OpenCode wrapper path is wired: `run-worker --mode opencode --opencode-variant max` runs the same assignment request. OpenCode/LLM output remains non-evidence.
- Accepted-evidence reuse is wired: `assign-slice --reuse-accepted-evidence --accepted-evidence-root validation/evidence --slice-spec <maintained-spec>` validates committed evidence inside an isolated worker output directory.
- Judge-facing before/after demo entrypoint: `docs/c2rust-migration-agent/judge-demo.md`. The preferred path uses `config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json` to generate `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`, `before-after-exhibit.json`, `milestone-release-report.json`, copied `target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json`, and `harness/judge-evidence-index.json`. The harness now exercises a real FlashDB `baseline_repair_gate`: attempt 1 records the unsafe baseline failure for `real-fdb-calc-crc32` with root cause `unsafe_baseline_requires_repair`, and retry attempt 2 requires the repair hint before revalidating accepted safe evidence. It shows unsafe 2 -> 0 and the planner/worker/verifier/repairer/reporter contract, while keeping `generated_draft_semantic_pass=false` and not increasing `translation_coverage_numerator`. The review gate only clears release-readiness review blockers; it is not a semantic acceptance gate. The tracked H4 run manifest is `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-h4-baseline-repair-run.json`.
- Judge-facing one-click runner: `python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json` executes the configured competition smoke, before/after, multi-worker, and OpenCode entrypoints in config order, then invokes the existing judge-entrypoint validator with local-artifact checks. Local artifact validation now binds `competition-smoke-summary.json` to the judge config `environment_profile.profile_id/sha256` and the entrypoint `proof_class/run_id`, and rejects CI/WSL/Windows-local evidence or `proof-class-limiting` deviations being mislabeled as `competition-exact`; the two `evaluate --profile` entrypoints also write `harness/resume-manifest.json`, a current-state resume index over the SQLite ledger, context pack, agent index, worker summaries, and resume entrypoints. `config/competition-env/bundle-manifest.json` also promotes the competition config folder to a hash-bound archive contract, and the runner report embeds a `competition_config_archive` snapshot. It also writes `summary/judge-milestone-bundle.json`, `summary/milestone-release-notes.md`, and `summary/public-release-packet.json`: the bundle aggregates `core_translation_quality`, `harness_architecture_summary`, `route_governance_metrics`, `evidence_cost_retention`, `claim_scope`, `proof_classes`, `publishability`, `known_gaps`, `must_not_claim`, and reproduction commands as the external review index; the Markdown release notes render a judge packet index with config/run/readiness/bundle refs; the JSON public release packet hash-binds the run report, readiness report, bundle, release notes, and config archive for quick judge review, then `validation.tools.validate_public_release_packet` checks it against `validation/public-release-packet.schema.json`, verifies the packet's copied publication manifest, known gaps, reproduction commands, and must-not-claim coverage against the bound bundle, and requires the release notes to match the Markdown rendered from that bundle. Use `--entrypoint-id before_after_judge_demo` for the focused before/after run or `--dry-run` to write only the execution plan. The smoke entrypoint is environment evidence only and keeps `semantic_gate=false`; the bundle, release notes, public release packet, and resume manifest are not semantic gates or translation-coverage numerators.
- `judge-milestone-bundle.json` now includes `harness_architecture_summary.contract_matrix`, a stage/role/artifact/validator/boundary matrix for `plan/translate/verify/repair/report`; the schema requires every row to keep `semantic_gate=false`, `chat_output_is_evidence=false`, and `translation_coverage_numerator=0`. The OpenCode `run-plan` graph now also exposes `opencode_worker.opencode_variant`, so reviewers do not need to drill into the preflight artifact to see the runtime variant.
- Judge-entrypoint local-artifact validation now also runs `validate_competition_run_summary.py` for non-smoke `competition_summary` artifacts, so workflow metrics, before/after artifact refs, repair history, unsafe accounting, final-gate rules, and slice counts are checked by the existing summary contract instead of only by path and sha256.
- Explicit multi-worker profile smoke: `config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json` fans out two source-pinned workers (`real-fdb-calc-crc32`, `real-fdb-blob-make`) and merges in planner order. The verified run `harness-flashdb-explicit-workers-20260701` passed with accepted-evidence `semantic_pass=2`; `evaluate --profile` with the same profile also passed and now emits `harness/evaluate-report.json` plus `harness/judge-evidence-index.json`. The index only binds verified batch artifacts by path and sha256. Semantic acceptance remains owned by accepted-evidence binding, the competition summary, workflow metrics, and validators; it is not a new semantic gate and does not increase `translation_coverage_numerator`. The tracked run manifest is `validation/evidence/flashdb/harness/l3-flashdb-explicit-workers-harness-run.json`.
- Profiles that enable route-governance metrics also emit and bind `summary/route-governance-metrics-report.json`; `validation/route-governance-metrics.schema.json` and the report `retention_policy` only lock the report fields, artifact-retention policy, and public-claim boundary. They do not promote accepted evidence, before/after exhibits, or route-governance metrics into translator-generated semantic pass, and they do not increase `translation_coverage_numerator`.
- C2Rust baseline manifest status now flows into route-governance metrics and the milestone scorecard: reports count manifest, generated-output, skipped, and compile-only states, then render the baseline comparison in release notes. These fields remain candidate context only with `semantic_gate=false` and `translation_coverage_numerator=0`.
- FlashDB slices currently passing through semantic evidence binding: `real-fdb-calc-crc32` and `real-fdb-blob-make`. Both are L4 accepted-evidence authoritative; generated drafts are still not semantic pass.
- FlashDB slice currently blocked: `real-fdb-kv-set`. Its direct callees have signature/source provenance, but `strlen`, `fdb_blob_make`, `fdb_kv_set_blob`, and `fdb_kv_del` shim/model/oracle semantics are not closed.

Key commands mirrored from the Chinese README:

```bash
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-blob-make --slice-spec validation/slice-specs/flashdb-real-fdb-blob-make.json --require-semantic-pass
python -m validation.tools.opencode_agent_harness run-worker --db target/competition-out/state/opencode-agent-harness.sqlite3 --run-id run-demo-001 --worker-id worker-a --mode deterministic
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
# Public review Markdown: target/competition-out-flashdb-judge-entrypoints/summary/milestone-release-notes.md
# Public release packet JSON: target/competition-out-flashdb-judge-entrypoints/summary/public-release-packet.json
python -B -m validation.tools.validate_public_release_packet --packet target/competition-out-flashdb-judge-entrypoints/summary/public-release-packet.json
# Evaluate resume index: target/competition-out-flashdb-*-evaluate-profile-20260701/harness/resume-manifest.json
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id before_after_judge_demo --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
```

## Maintenance Notes

- Keep filenames paired as `README.md` and `README.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `README.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

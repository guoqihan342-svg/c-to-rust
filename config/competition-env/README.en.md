# Competition Environment Configuration

This directory is the standalone entrypoint for the competition/evaluation environment. Code, scripts, and validation gates should be adapted to these constraints; do not treat the local Windows toolchain, historical evidence, or validation compatibility copies as the source of truth.

## Baseline

- OS: Ubuntu 24.04.4 LTS (Noble Numbat)
- Kernel: `5.10.0-182.0.0.95.r194_123.hce2.x86_64`
- APT mirror: `http://mirrors.tools.huawei.com/ubuntu`
- Python: `3.12.3`
- pip: `24.0`
- PyPI mirror: `https://mirrors.tools.huawei.com/pypi/simple`
- Node.js: `v24.13.0`
- npm: `11.6.2`
- npm registry: `https://mirrors.tools.huawei.com/npm/`
- Java: OpenJDK `21.0.10` (`bisheng_jdk_enterprise`)
- Maven: `3.9.11`
- `MAVEN_HOME`: `/usr/local/maven3`
- Rust: `1.96.0`
- Cargo: `1.96.0`
- Cargo registry: `sparse+http://rust.inhuawei.com/crates.io-index/`
- Go: not installed
- gcc: `13.3.0`
- g++: `13.3.0`
- GNU Make: `4.3`
- CMake: not found
- clang: not required by default; the typed-IR competition lane requires either `CLANG_PATH` or a project-local vendored clang binary

## FlashDB Source Pin

`environment.json.source_pins.flashdb` fixes the competition-scoring source to `https://gitcode.com/xwxf/FlashDB.git`, the `competition` branch, and commit `f9d0421315c564fb890a1b14eee77b290e0d7bbe`; the corresponding checkout command is `git checkout -b competition f9d0421315c564fb890a1b14eee77b290e0d7bbe`. New competition-targeted extraction must pass `--source-repository`, `--source-branch`, and `--require-source-commit` so `extract_source_slice.py` validates the real checkout before writing a slice spec.

## Files

- `environment.json`: machine-readable baseline, mirrors, and adaptation policy.
- `bundle-manifest.json`: machine-readable archive contract for this competition config directory. It hash-binds the environment profile, mirror configs, shell entrypoints, planned batch profiles, judge entrypoint index, review checklist, and OpenCode runbook; through `external_refs` it also binds `requirements.txt`, `opencode.json`, the FlashDB bootstrap script, the core CI workflow, the repo-owned skill, and `.opencode/agents/c2rust-migrator.md`. `validate_judge_entrypoints` verifies it, but it is not a semantic gate.
- `apt/sources.list`: Ubuntu Noble APT mirror configuration.
- `pip/pip.conf`: pip mirror configuration.
- `npm/.npmrc`: npm registry configuration.
- `cargo/config.toml`: Cargo crates.io mirror configuration; `env.sh` points `CARGO_HOME` at this directory's `cargo/` folder so Cargo uses the mirror without mutating the user's global configuration.
- `rust/rust-toolchain.toml`: Rust `1.96.0` toolchain declaration; it is not active at the repository root by default.
- `env.sh`: shell environment entrypoint for the competition host, including local clang auto-detection.
- `toolchain-check.sh`: competition host self-check script.
- `smoke.sh`: lightweight Linux/WSL/CI smoke wrapper; it calls `run_competition_smoke.py` and emits a proof-classed summary. Use the Python entrypoint directly when an explicit `run-id` or timeout is needed.
- `planned-batches/`: reusable planned batch profile inputs; `run-batch-profile` invokes `init-run`, `plan-source-file`, and `run-plan --execute-merge` from the profile, can enable `run-plan --auto-retry` when `auto_retry=true`, and can fan out independent workers with `max_workers`.
- `judge-entrypoints/`: judge-facing one-command entrypoint directory. `flashdb-harness.json` now binds the competition environment smoke, FlashDB before/after demo, explicit multi-worker evaluate profile, and OpenCode multi-worker evaluate profile. The smoke entrypoint writes `target/competition-smoke-flashdb-judge-entrypoint/summary/competition-smoke-summary.json` and proves environment/toolchain gates only; it is not a semantic gate. To run all configured judge entrypoints, omit `--entrypoint-id`: `python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json`. For a focused before/after run, add `--entrypoint-id before_after_judge_demo`. Add `--dry-run` to emit only the execution plan. For index-only validation, run `python3 -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json`; public entrypoint and tracked reproduction commands are pinned to portable `python3 -B`, while the local runner resolves them to a runnable non-absolute Python launcher. Add `--require-local-artifacts` after local target artifacts have been generated to deep-check smoke summary, vendored-clang verification artifact, context-pack, agent-index, resume-manifest, judge-evidence-index, route-governance metrics schema, OpenCode preflight/worker launch policy, and worker-index consistency. `resume-manifest.json` is the current-state resume index for the two `evaluate --profile` entrypoints, binding the SQLite ledger, context pack, agent index, worker summaries, repair hints, and resume entrypoints; it is not an executor and not a semantic gate. Judge-evidence-index deep validation now requires `harness_architecture.context_pack/agent_index` to explicitly bind the expected artifacts and `evidence_artifact_refs`, preventing the architecture view from drifting away from the judge evidence index. Artifact JSON portability scans also reject Windows, WSL, and Linux local absolute paths; only diagnostic host metadata and merge execution traces may retain host paths in whitelisted positions. The same validator also checks the config archive bundle. Smoke summary deep validation binds `profile_id/profile_sha256` to `environment_profile`, binds `proof_class/run_id` to the entrypoint, and rejects CI/WSL/Windows-local evidence or `proof-class-limiting` deviations being labeled `competition-exact`; vendored-clang verification deep validation binds `status/reason/final_gate/clang_lane_verified` to the smoke summary so `missing_clang_path` cannot be misread as a verified clang lane. A successful all-entrypoints runner also writes `target/competition-out-flashdb-judge-entrypoints/summary/judge-milestone-bundle.json` and `milestone-release-notes.md`. The bundle binds the run report, readiness report, post-run expected artifacts, workflow metrics, route-governance metrics, OpenCode runtime, `core_translation_quality`, `harness_architecture_summary`, `claim_scope`, `proof_classes`, `publishability`, `quantitative_evaluation`, `publication_manifest`, `known_gaps`, `must_not_claim`, and `reproduction_commands` for external review; the Markdown release notes are a human-readable public packet rendered from the bundle. `quantitative_evaluation` provides a machine-readable scorecard for workflow, route, blocked-repair, unsafe, and baseline-comparison metrics, while `publication_manifest` binds the repo commit, FlashDB source pin, judge config, competition config archive, run-report/bundle, supported subset, known gaps/non-goals, and claim boundary. These artifacts are evidence indexes, not semantic gates or translation-coverage numerators; the release notes and resume manifest are runtime outputs and are not part of `bundle-manifest.json`.
- Focused `--entrypoint-id` runs are smoke/triage tools, not full release packets. After successful focused commands, the runner writes `selected-entrypoints-validation-config.json` next to the run report, and post-run `--require-local-artifacts` deep validation checks only the entrypoints executed in that run while narrowing `test_contract.required_entrypoint_ids`; runs without `--entrypoint-id` still validate the complete `flashdb-harness.json` entrypoint set.
- `validate_judge_entrypoints` also accepts `--entrypoint-id` for direct focused index or local-artifact validation. It narrows `test_contract.required_entrypoint_ids` in the same way, and unknown entrypoint ids fail closed. This mode is for H8/H9 staged reproduction and triage only; it does not replace the full runner or real GLM/OpenCode host acceptance.
- Non-smoke summary deep validation: when `--require-local-artifacts` is enabled, `validate_judge_entrypoints` now sends every non-smoke `competition_summary` through `validate_competition_run_summary.py` after the entrypoint identity checks. This prevents a hash-correct summary from drifting in workflow metrics, before/after refs, repair history, unsafe accounting, final-gate rules, or slice counts.
- Harness contract matrix: `judge-milestone-bundle.json` now exposes `harness_architecture_summary.contract_matrix`, grouping `plan/translate/verify/repair/report` by roles, artifacts, validators, and non-semantic boundaries. The schema keeps every row at `semantic_gate=false`, `chat_output_is_evidence=false`, and `translation_coverage_numerator=0`; OpenCode run-plan graph contracts also expose `opencode_worker.opencode_variant`.
- C2Rust baseline scoring boundary: route-governance metrics summarize generated/skipped/output/compile status from `*-c2rust-baseline-manifest.json`, the milestone bundle deduplicates by evidence root into `quantitative_evaluation.baseline_comparison.raw_c2rust.c2rust_baseline_rollup`, and release notes render manifest/source/compile-pass counts. These fields are not semantic gates and never promote C2Rust compile success into semantic pass.
- Public release packet output: the same successful runner also emits `target/competition-out-flashdb-judge-entrypoints/summary/public-release-packet.json`, a hash-bound index over the run report, readiness report, milestone bundle, Markdown release notes, and competition config archive. `validation.tools.validate_public_release_packet` validates the packet schema, hashes, claim boundary, local-path hygiene, consistency between the packet's copied `publication_manifest`, `quantitative_evaluation`, `progress_delta_ledger`, `summary.workflow_metrics`, `summary.progress_delta_ledger`, known gaps, reproduction commands, and must-not-claim entries and the bound milestone bundle, and release-notes consistency against the bundle-rendered Markdown. It is a judge-facing package index only, not a semantic gate and not part of `bundle-manifest.json`.
- OpenCode safety-transform attempt publication: the OpenCode evaluate entrypoint declares `expected_artifacts.opencode_safety_transform_attempt`, and `judge-evidence-index.json` promotes the worker-side `opencode-safety-transform-attempt-<attempt>.json` into top-level `evidence_artifact_refs`, so the milestone bundle and public release packet can expose it through `publication_manifest.published_artifact_refs`. This artifact only audits the OpenCode command contract, one-patch-per-round rule, five-round cap, rollback/retry evidence, and unsafe-delta binding; it is not a semantic gate and does not increase `translation_coverage_numerator`.
- S4 progress delta: the milestone bundle now emits `progress_delta_ledger`, separating capability delta, governance/evidence delta, and workflow repair delta. When workflow repair activity is sparse, the ledger fills repair, auto-recovery, rollback-evidence, and source counts from verified `before_after_repair_exhibit` evidence by entrypoint. The public release packet copies that ledger, and release notes render a `Progress Delta Ledger` table. This view is for reviewer navigation only and does not change the semantic gate, generated-draft pass state, or translation coverage numerator.
- OpenCode diagnostic redaction: worker repair diagnostics replace Windows, WSL, and Linux local absolute paths in stdout/stderr/python traceback tails with `<local-absolute-path>` before those diagnostics enter repair hints, agent indexes, resume manifests, or judge evidence. Path-governance violations fail closed as harness evidence instead of leaking into the public packet.
- `review-checklists/`: milestone/release review gate input directory. `flashdb-harness-internal-review.json` records human review coverage for harness architecture, unsafe ledger, coverage matrix, real-slice evidence, public claim boundaries, and known refusals. `milestone_release_report.py --review-checklist ...` consumes it as release-readiness input; `judge_demo.py --review-checklist ...` copies it to `summary/milestone-review-checklist.json` under the out-root and has `harness/judge-evidence-index.json` bind both the original input and copied run artifact. The review checklist is not a semantic gate.
- `opencode-single-interaction.md` / `.en.md`: OpenCode single-interaction competition workflow guide; OpenCode preflight reports must match both the current `run_id` and launch policy, so preflight from an older run cannot be reused.
- Windows/OpenCode preflight status: earlier focused local `opencode_multi_worker_evaluate_profile` evidence is historical pre-GLM-gate evidence. Current OpenCode evidence must first prove `GLM-5.1` availability through `opencode models`; `environment.json` now carries the machine-readable `opencode_runtime` contract for this requirement, and `toolchain-check.sh` reports OpenCode/GLM status by default while `REQUIRE_OPENCODE_GLM=1` turns missing OpenCode, probe failure, or a model list without GLM into a hard failure. If the model list omits GLM, preflight fails closed with `opencode_model_unavailable` / `required_model_not_listed`, `opencode_run_launched=false`, and no marker. local-simulation OpenCode pass does not close P0-H9; regenerate the OpenCode artifacts on the competition GLM/OpenCode host or an equivalent provider configuration before using `--require-local-artifacts` as current OpenCode evidence. This remains runtime/reproduction evidence only, not a semantic gate, and it does not change `translation_coverage_numerator`.

## Clang Policy: Project-Local Vendored Binary

The competition host does not install clang by default, but the project may carry a clang binary inside the repository:

```
repository root/
├── tools/
│   ├── llvm/bin/clang          # recommended on Linux
│   ├── llvm/bin/clang-18       # recommended versioned Linux path
│   ├── llvm/bin/clang.exe      # recommended on Windows
│   ├── clang/bin/clang         # fallback path
│   └── ...
```

Workflow:

1. Copy a compatible clang binary from an existing installation into `tools/llvm/bin/`.
2. `env.sh` auto-detects it and exports `CLANG_PATH`.
3. When `toolchain-check.sh` finds clang, it also runs `-print-resource-dir` and a minimal TU AST-dump smoke over a file including `stdint.h`/`stddef.h`, proving resource-dir, standard headers, and include search paths are usable.
4. `auto_migrate.py --competition-clang-lane` prefers `CLANG_PATH`; when it is unset, the tool searches the project-local paths above.
5. If neither source is available, the lane returns `missing_clang_path`.

Run the standalone verifier when machine-readable evidence is needed:

```bash
python3 -B validation/tools/verify_vendored_clang.py \
  --proof-class wsl-local-simulation \
  --out target/competition-smoke/summary/vendored-clang-verification.json
```

When clang is missing, this verifier writes `status=missing` / `reason=missing_clang_path` without failing the default non-clang route. With `--require-clang`, the same missing state fails the final gate. When clang is present, it records the clang source, version, `-print-resource-dir`, `-E -v` include search paths, the minimum TU AST dump containing `stdint.h`/`stddef.h`, command logs, and repo/out-root-relative artifact paths.

Rationale: clang is used only for `-ast-dump=json`; the lane does not require libclang, CMake, or a system-wide LLVM installation.

## Adaptation Rules

- Default build, test, and validation paths must not require Go.
- Default build, test, and validation paths must not require CMake; C/C++ oracle paths should prefer `gcc`, `g++`, and GNU Make.
- Default build, test, and validation paths must not require a system clang install. When the real clang AST dump typed-IR lane is needed, use `CLANG_PATH` as a command name on `PATH` or as a repo-local path, or use a project-local vendored clang binary under the repo root (`tools/llvm/bin/clang-18`, `tools/llvm/bin/clang`, or `tools/clang/bin/clang`), then run `auto_migrate.py --competition-clang-lane`; path-like `CLANG_PATH` values that resolve outside the repo fail closed as `invalid_clang_path_outside_repo`. That lane must fail clearly if neither source is available. When clang is present, `toolchain-check.sh` runs the minimum TU smoke.
- The Huawei Cargo mirror is activated by `env.sh` through `CARGO_HOME=config/competition-env/cargo`; do not rely only on the existence of `cargo/config.toml`, and do not mutate the user's global Cargo configuration by default.
- Rust code must remain compatible with stable Rust `1.96.0` and must not use nightly-only features.
- Python scripts should target Python `3.12.3` / pip `24.0`.
- Node/npm scripts should target Node `v24.13.0` / npm `11.6.2`.
- Direct dependencies must be admitted by `environment.json.dependency_admission_policy`. Before adding libclang, bindgen, syn, quote, tracing, anyhow, or any other dependency, record the concrete semantic risk, generation-quality risk, or maintainability risk it removes, and prove it does not break the default competition profile.
- Newly generated validation evidence should record `profile_id=huawei-competition-ubuntu-24.04` plus the `environment.json` hash.

## Usage

On the competition host:

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

After `env.sh`, `CARGO_HOME` points to `config/competition-env/cargo`, so Cargo reads its `config.toml` and uses the Huawei sparse registry.

Lightweight Linux/WSL/CI smoke entrypoint:

```bash
# Use ci-approximation in CI, wsl-local-simulation under WSL, and local-simulation on local hosts.
bash config/competition-env/smoke.sh ci-approximation target/competition-smoke

# Equivalent Python entrypoint with an explicit run id.
python3 -B validation/tools/run_competition_smoke.py \
  --proof-class ci-approximation \
  --run-id core-ci-smoke \
  --timeout-seconds 600 \
  --out-root target/competition-smoke
```

The smoke runs the environment check, the structured vendored clang verifier, the core committed evidence validator, `evidence_governance.py`, `translator_coverage_matrix.py`, and a lightweight unittest subset. It writes `target/competition-smoke/summary/competition-smoke-summary.json` with `execution_environment`, `competition_profile_match`, `environment_deviations`, `clang_source`, `vendored_clang_verification.path`, gate status, and log paths. The Python entrypoint defaults to a 600-second per-step timeout; timeouts are written to `timeout_policy` and the affected step, use exit code 124, and must trigger a final-gate failure. `validate_judge_entrypoints --require-local-artifacts` rejects missing or drifted timeout policies, rejects non repo-relative or parent-traversing expected artifact and smoke summary artifact paths, and reads `commands.jsonl` to reject local absolute command arguments, including local host paths embedded in shell fragments; the runner normalizes those paths to basenames before writing the command log. In non-`competition-exact` proof classes, missing clang is recorded as `missing_clang_path` in `vendored-clang-verification.json`; path-like `CLANG_PATH` values outside the repo are recorded as `invalid_clang_path_outside_repo` and fail closed; `competition-exact` treats the vendored clang verifier as a required gate. Missing required C compilers such as `gcc`/`g++` are not ordinary proof-class drift: the summary step records `failure_class=required_c_compiler_missing` and fails closed. Do not pass `competition-exact` unless running on the real competition host with external environment proof; that mode requires both `--confirm-competition-exact` and `COMPETITION_EXACT_HOST=1`, and the runner fails closed when `ci-approximation` or `wsl-local-simulation` is requested on an incompatible host. The smoke does not translate a new slice and does not claim a new semantic pass.

The judge-facing smoke entrypoint uses the same runner with `--out-root target/competition-smoke-flashdb-judge-entrypoint`; its summary has `report_kind=competition-smoke-summary` and `claim_boundary.semantic_gate=false`, and `validate_judge_entrypoints --require-local-artifacts` checks the summary, vendored-clang verification, evidence governance report, coverage matrix, milestone report, and command log paths. The same local-artifact gate also verifies that the summary `profile_id/profile_sha256/proof_class/run_id` match `flashdb-harness.json`, binds `vendored-clang-verification.json` `status/reason/final_gate/clang_lane_verified` to the summary, and rejects non repo-relative `clang.path`, expected artifact paths, smoke artifact paths, missing judge-evidence-index architecture refs for context/agent artifacts, Windows/WSL/Linux local absolute paths in artifact JSON, plus local absolute paths in `commands.jsonl.command`; local/WSL/CI runs mislabeled as `competition-exact`, missing exact-host attestation, non-CI runs labeled `ci-approximation`, non-WSL runs labeled `wsl-local-simulation`, missing clang mislabeled as a verified clang lane, local absolute clang paths, stale command logs, command logs with host-specific Python executable paths, or shell fragments leaking `/mnt/...`, `\\wsl$...`, or `//wsl.localhost/...` host paths fail closed.

Judge-facing one-click harness runner:

```bash
python3 -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json

python3 -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --entrypoint-id before_after_judge_demo \
  --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json

python3 -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --dry-run
```

The runner performs entrypoint preflight without requiring local artifacts before executing commands. Every entrypoint command has a finite 36000-second default timeout, overrideable with `--timeout-seconds`; a timeout is recorded in the run report under `entrypoint.timeout_policy` and fails closed as `root_cause_key=process_timeout` / `exit_code=124`. After successful commands, it invokes local-artifact deep validation and writes the readiness report. The run report embeds `competition_config_archive`, binding the current `config/competition-env` file snapshot by path and sha256; the validator also checks the directory-level `bundle-manifest.json` contract. The two `evaluate --profile` entrypoints write `harness/resume-manifest.json` as a current-state resume index, and the validator checks repo-relative paths, context/agent hashes, the SQLite ledger, worker count, `resume_manifest.workers` consistency with the context-pack/agent-index worker sets and artifact fields, and the `semantic_gate=false` / `translation_coverage_numerator=0` boundary. On successful non-dry-run execution it also writes `judge-milestone-bundle.json` and `milestone-release-notes.md` next to the run report. The bundle hashes the run report and validator-owned artifact refs, and marks focused runs as not externally publishable; the release notes are rendered from the bundle afterward and do not write back into the bundle hash chain. Its one-screen fields include `core_translation_quality`, `harness_architecture_summary`, `route_governance_metrics`, `evidence_cost_retention`, the proof-class rollup, publishability, quantitative evaluation scorecard, publication manifest, unsafe-reduction scope, OpenCode evidence policy, known gaps, must-not-claim list, and reproduction commands. These fields are for judge review only and do not expand semantic acceptance. `quantitative_evaluation` is derived only from existing rollups for workflow units, outcome counts, unsafe reduction, repair activity, and baseline comparison; the public release packet now also copies that scorecard plus `summary.workflow_metrics.repair_activity` as machine-readable judge context and validates both against the bundle. `publication_manifest` is an external publication-package index; the bundle records its own repo-relative path but does not embed its own sha256, avoiding a recursive hash. `validation/tools/milestone_release_notes.py` renders that public index to Markdown and refuses semantic-gate, translator-generated-pass, coverage-numerator, raw-C2Rust semantic-acceptance, or OpenCode-chat-evidence overclaims before writing notes. `validation/judge-milestone-bundle.schema.json` is the machine contract for this public index: the run report must declare `schema_version=1` / `report_kind=judge-entrypoints-run-report`, proof class is trusted only from the validator-owned `validation.proof_class_contract`, and missing or conflicting contract data makes the bundle fail closed. It is orchestration evidence only; semantic acceptance remains owned by the competition summary, workflow metrics, oracle evidence, and validators.

Reusable planned batch profile entrypoint:

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json \
  --run-id flashdb-fdb-utils-local \
  --out-root target/competition-out
```

This profile only makes `init-run`, `plan-source-file` or explicit `workers[]` planning, and `run-plan --execute-merge` reproducible as one command. Semantic acceptance still comes only from the final `competition-run-summary.json`, workflow metrics, and validators. The current FlashDB profile reuses committed accepted-evidence bindings and explicitly records `generated_draft_semantic_pass=false`; do not interpret it as the regenerated Rust draft itself passing the semantic gate. The before/after, accepted-evidence, and demo exhibit profiles use `auto_retry=true` / `max_workers=4`; the explicit multi-worker evaluate and OpenCode evaluate profiles use `auto_retry=false` / `max_workers=2` to show deterministic fan-out/fan-in. Retries only let failed workers consume persisted repair hints up to the five-round cap, while `max_workers` is LangGraph-style worker fan-out with planner-order fan-in. `--mode opencode` also has a narrow startup retry for transient OpenCode `database is locked` failures before the first shell command; that retry is recorded as `opencode_process_retries` and does not bypass contract verification, summaries, or validators. Neither retry path replaces the validator.

When a profile enables `emit_route_governance_metrics_report=true`, `run-batch-profile` / `evaluate --profile` also binds `summary/route-governance-metrics-report.json`; `validation/route-governance-metrics.schema.json` validates the report claim boundary, denominators, separated counts, S2 workflow summary, and `retention_policy`. The report and `retention_policy` constrain public claims and artifact retention only; they are not a semantic gate and do not increase `translation_coverage_numerator`.

Judge-facing before/after demo profile:

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json \
  --run-id competition-demo-before-after-exhibit \
  --out-root target/competition-out-demo-before-after-exhibit

python3 -B validation/tools/validate_competition_run_summary.py \
  --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
```

This profile generates `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json` and binds `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json`. It demonstrates accepted-evidence before/after artifacts, unsafe 3 -> 0, `auto_retry=true`, and the harness five-stage contract; `generated_draft_semantic_pass=false`, and it does not increase `translation_coverage_numerator`.

The clang typed-IR competition lane is explicit opt-in:

```bash
# Option 1: explicit CLANG_PATH through PATH, without storing a host absolute path
export CLANG_PATH="clang"
python3 -B validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane

# Option 2: project-local clang detected by env.sh
source config/competition-env/env.sh
python3 -B validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane
```

For committed or judge-facing evidence, do not set `CLANG_PATH="$(command -v clang)"`: the structured verifier rejects path-like `CLANG_PATH` values that resolve outside the repository and normalizes repo-local clang paths in command logs.

Passing only `--emit-clang-lowering-report` remains diagnostic mode; when clang is missing it writes an unavailable report and does not turn the default non-clang lane into a failure.

If package-manager configuration needs to be installed into the user profile, sync the matching files from this directory to each tool's default location. This repository does not mutate global user configuration automatically.

## Relation To validation/

`validation/environment-profiles/huawei-competition-ubuntu-24.04/` is now a README-only historical redirect. The new default configuration entrypoint is this directory; validation evidence may retain the old path as a historical reference, but new scripts must use `config/competition-env/environment.json`.

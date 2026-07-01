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
- `apt/sources.list`: Ubuntu Noble APT mirror configuration.
- `pip/pip.conf`: pip mirror configuration.
- `npm/.npmrc`: npm registry configuration.
- `cargo/config.toml`: Cargo crates.io mirror configuration; `env.sh` points `CARGO_HOME` at this directory's `cargo/` folder so Cargo uses the mirror without mutating the user's global configuration.
- `rust/rust-toolchain.toml`: Rust `1.96.0` toolchain declaration; it is not active at the repository root by default.
- `env.sh`: shell environment entrypoint for the competition host, including local clang auto-detection.
- `toolchain-check.sh`: competition host self-check script.
- `smoke.sh`: lightweight Linux/WSL/CI smoke entrypoint; it calls `run_competition_smoke.py` and emits a proof-classed summary.
- `planned-batches/`: reusable planned batch profile inputs; `run-batch-profile` invokes `init-run`, `plan-source-file`, and `run-plan --execute-merge` from the profile, can enable `run-plan --auto-retry` when `auto_retry=true`, and can fan out independent workers with `max_workers`.
- `judge-entrypoints/`: judge-facing one-command entrypoint directory. `flashdb-harness.json` now binds the competition environment smoke, FlashDB before/after demo, explicit multi-worker evaluate profile, and OpenCode multi-worker evaluate profile. The smoke entrypoint writes `target/competition-smoke-flashdb-judge-entrypoint/summary/competition-smoke-summary.json` and proves environment/toolchain gates only; it is not a semantic gate. To run all configured judge entrypoints, omit `--entrypoint-id`: `python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json`. For a focused before/after run, add `--entrypoint-id before_after_judge_demo`. Add `--dry-run` to emit only the execution plan. For index-only validation, run `python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json`; add `--require-local-artifacts` after local target artifacts have been generated to deep-check smoke summary, context-pack, agent-index, judge-evidence-index, and worker-index consistency. A successful all-entrypoints runner also writes `target/competition-out-flashdb-judge-entrypoints/summary/judge-milestone-bundle.json`, which binds the run report, readiness report, post-run expected artifacts, workflow metrics, and OpenCode runtime summaries for external review; it is an evidence index, not a semantic gate or translation-coverage numerator.
- `review-checklists/`: milestone/release review gate input directory. `flashdb-harness-internal-review.json` records human review coverage for harness architecture, unsafe ledger, coverage matrix, real-slice evidence, public claim boundaries, and known refusals. `milestone_release_report.py --review-checklist ...` consumes it as release-readiness input; `judge_demo.py --review-checklist ...` copies it to `summary/milestone-review-checklist.json` under the out-root and has `harness/judge-evidence-index.json` bind both the original input and copied run artifact. The review checklist is not a semantic gate.
- `opencode-single-interaction.md` / `.en.md`: OpenCode single-interaction competition workflow guide.

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
python validation/tools/verify_vendored_clang.py \
  --proof-class wsl-local-simulation \
  --out target/competition-smoke/summary/vendored-clang-verification.json
```

When clang is missing, this verifier writes `status=missing` / `reason=missing_clang_path` without failing the default non-clang route. With `--require-clang`, the same missing state fails the final gate. When clang is present, it records the clang source, version, `-print-resource-dir`, `-E -v` include search paths, the minimum TU AST dump containing `stdint.h`/`stddef.h`, command logs, and repo/out-root-relative artifact paths.

Rationale: clang is used only for `-ast-dump=json`; the lane does not require libclang, CMake, or a system-wide LLVM installation.

## Adaptation Rules

- Default build, test, and validation paths must not require Go.
- Default build, test, and validation paths must not require CMake; C/C++ oracle paths should prefer `gcc`, `g++`, and GNU Make.
- Default build, test, and validation paths must not require a system clang install. When the real clang AST dump typed-IR lane is needed, use `CLANG_PATH` or a project-local vendored clang binary under the repo root (`tools/llvm/bin/clang-18`, `tools/llvm/bin/clang`, or `tools/clang/bin/clang`), then run `auto_migrate.py --competition-clang-lane`; that lane must fail clearly if neither source is available. When clang is present, `toolchain-check.sh` runs the minimum TU smoke.
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
python validation/tools/run_competition_smoke.py \
  --proof-class ci-approximation \
  --run-id core-ci-smoke \
  --out-root target/competition-smoke
```

The smoke runs the environment check, the structured vendored clang verifier, the core committed evidence validator, `evidence_governance.py`, `translator_coverage_matrix.py`, and a lightweight unittest subset. It writes `target/competition-smoke/summary/competition-smoke-summary.json` with `execution_environment`, `competition_profile_match`, `environment_deviations`, `clang_source`, `vendored_clang_verification.path`, gate status, and log paths. In non-`competition-exact` proof classes, missing clang is recorded as `missing_clang_path` in `vendored-clang-verification.json`; `competition-exact` treats the vendored clang verifier as a required gate. Do not pass `competition-exact` unless running on the real competition host with external environment proof; that mode requires `--confirm-competition-exact` by default so CI/WSL/local output is not mislabeled as exact competition evidence. The smoke does not translate a new slice and does not claim a new semantic pass.

The judge-facing smoke entrypoint uses the same runner with `--out-root target/competition-smoke-flashdb-judge-entrypoint`; its summary has `report_kind=competition-smoke-summary` and `claim_boundary.semantic_gate=false`, and `validate_judge_entrypoints --require-local-artifacts` checks the summary, vendored-clang verification, evidence governance report, coverage matrix, milestone report, and command log paths.

Judge-facing one-click harness runner:

```bash
python -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json

python -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --entrypoint-id before_after_judge_demo \
  --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json

python -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --dry-run
```

The runner performs entrypoint preflight without requiring local artifacts before executing commands. After successful commands, it invokes local-artifact deep validation and writes the readiness report. On successful non-dry-run execution it also writes `judge-milestone-bundle.json` next to the run report; that bundle hashes the run report and validator-owned artifact refs, and marks focused runs as not externally publishable. It is orchestration evidence only; semantic acceptance remains owned by the competition summary, workflow metrics, oracle evidence, and validators.

Reusable planned batch profile entrypoint:

```bash
python -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json \
  --run-id flashdb-fdb-utils-local \
  --out-root target/competition-out
```

This profile only makes `init-run`, `plan-source-file` or explicit `workers[]` planning, and `run-plan --execute-merge` reproducible as one command. Semantic acceptance still comes only from the final `competition-run-summary.json`, workflow metrics, and validators. The current FlashDB profile reuses committed accepted-evidence bindings and explicitly records `generated_draft_semantic_pass=false`; do not interpret it as the regenerated Rust draft itself passing the semantic gate. The before/after, accepted-evidence, and demo exhibit profiles use `auto_retry=true` / `max_workers=4`; the explicit multi-worker evaluate and OpenCode evaluate profiles use `auto_retry=false` / `max_workers=2` to show deterministic fan-out/fan-in. Retries only let failed workers consume persisted repair hints up to the five-round cap, while `max_workers` is LangGraph-style worker fan-out with planner-order fan-in. Neither replaces the validator.

Judge-facing before/after demo profile:

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json \
  --run-id competition-demo-before-after-exhibit \
  --out-root target/competition-out-demo-before-after-exhibit

python -B validation/tools/validate_competition_run_summary.py \
  --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
```

This profile generates `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json` and binds `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json`. It demonstrates accepted-evidence before/after artifacts, unsafe 3 -> 0, `auto_retry=true`, and the harness five-stage contract; `generated_draft_semantic_pass=false`, and it does not increase `translation_coverage_numerator`.

The clang typed-IR competition lane is explicit opt-in:

```bash
# Option 1: explicit CLANG_PATH
export CLANG_PATH="$(command -v clang)"
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane

# Option 2: project-local clang detected by env.sh
source config/competition-env/env.sh
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane
```

Passing only `--emit-clang-lowering-report` remains diagnostic mode; when clang is missing it writes an unavailable report and does not turn the default non-clang lane into a failure.

If package-manager configuration needs to be installed into the user profile, sync the matching files from this directory to each tool's default location. This repository does not mutate global user configuration automatically.

## Relation To validation/

`validation/environment-profiles/huawei-competition-ubuntu-24.04/` is now a README-only historical redirect. The new default configuration entrypoint is this directory; validation evidence may retain the old path as a historical reference, but new scripts must use `config/competition-env/environment.json`.

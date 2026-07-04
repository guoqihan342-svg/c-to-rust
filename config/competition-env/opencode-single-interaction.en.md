# OpenCode Single-Interaction Competition Workflow

Chinese original: `opencode-single-interaction.md`.

## Overview

The competition evaluation model: OpenCode reads this repository and completes the C-to-Rust migration in a **single interaction**. If the evaluator sets a **600-minute (10-hour)** timeout cap, treat it as an external budget reference. This project still optimizes for accuracy first, not for saving time at the cost of validation. No multi-round prompt tuning, no mid-session branch switching, no external human intervention.

## Competition Agent Runtime Contract

Judge-facing agent evidence recognizes exactly one launch policy: command `opencode`, model `GLM-5.1`, repo-owned agent `c2rust-migrator`, and variant `max`. Every OpenCode preflight, worker, resume replay, and public packet artifact must preserve machine-checkable fields equivalent to `--opencode-model GLM-5.1 --opencode-agent c2rust-migrator --opencode-variant max`.

`opencode-preflight` must first run `opencode models` under the same repo-local runtime env and prove that the model list contains the exact `GLM-5.1` token. If the model is unavailable, the command is not `opencode`, the agent is not `c2rust-migrator`, the variant is not `max`, or preflight/session/handoff evidence is missing, the harness must fail closed, record `opencode_model_unavailable` or the corresponding launch-contract blocker, and must not launch workers or publish the result as passing competition evidence.

Codex chat, Codex subagents, other OpenCode models, local `local-simulation`, and hand-edited artifacts are development aids only. They cannot close P0-H9, cannot be labeled competition-facing agent evidence, and cannot replace the C oracle / Rust replay / diff / unsafe ledger / final validator chain. OpenCode chat/session text is command-contract audit evidence only; semantic acceptance comes only from on-disk artifacts and validators.

## Goal

Complete within one OpenCode session:

```
Input: repository
  ↓ OpenCode single interaction
Output: real C source function → Rust translation + L3 semantic-pass evidence
```

Standalone handoff files such as `CONTEXT.md` are not maintained; current state and next steps live in `docs/c2rust-migration-agent/future-vision-and-mvp.md`. They are not judge inputs, release documents, evidence sources, or entrypoints.

Output requirements:
- At least one real C source function with a complete evidence chain: typed IR → Rust draft → C oracle → Rust replay → diff → negative diff → final verification
- Evidence validated by `validate_auto_translation_evidence.py --require-semantic-pass`
- All auto-translation evidence bound to the competition environment profile
- First-party non-test `unsafe` ratio auditable (ideally 0%)

## Single-Interaction Design Principles

To maximize semantic accuracy within one interaction, the project architecture follows these principles:

1. **One prompt, full pipeline.** No agent loop, no multi-turn dialogue, no human mid-process decisions.
2. **Parallelism is allowed, but evidence must converge through one gate.** Multiple subagents or batch workers may process independent slices. Each worker must write to an isolated output directory, and the common validator/final verification must aggregate the result. An agent's conversational judgment is never acceptance evidence.
3. **Fail-closed; do not loosen gates to save time.** When the translator encounters an unsupported C construct, it refuses and records the reason. Only deterministically-passing candidates enter the validation pipeline.
4. **Evidence-driven, not dialogue-driven.** Correctness depends on machine-verifiable evidence (C oracle + Rust replay + diff + negative diff), not on agent conversational skill.

## Pipeline and Reference Time Estimates

These estimates are only for planning, not acceptance criteria. Competition and development both prioritize semantic accuracy and evidence completeness. Per-slice estimates using `auto_migrate.py` (real C source function, with clang lowering):

| Stage | Operation | Estimated |
|-------|-----------|-----------|
| 1 | Environment check (`env.sh` + `toolchain-check.sh`) | < 1 min |
| 2 | Real-source function slice extraction (`extract_source_slice.py`) | < 1 min |
| 3 | Clang AST dump (`-Xclang -ast-dump=json -fsyntax-only`) | < 1 min |
| 4 | Typed IR lowering + generic emitter + Rust draft | < 1 min |
| 5 | Rust draft compilation check (`rustc` / `cargo check`) | < 2 min |
| 6 | C oracle harness draft + compile + execute | < 3 min |
| 7 | Rust replay compile + execute | < 3 min |
| 8 | Schema-aware diff + negative diff | < 2 min |
| 9 | Unsafe scan + unsafe ledger | < 1 min |
| 10 | Full evidence validation (`--require-semantic-pass`) | < 3 min |
| 11 | OpenSpec validate + CI checks | < 2 min |
| **Total estimate** | | **< 20 min / slice** |

For FlashDB crc32 (the proven case): typed IR candidate generation to validation profile generation takes ~5-8 minutes.

**Multi-slice strategy**: the same OpenCode session may process multiple independent slices in parallel. Parallel runs must give each slice/worker an isolated out-root or subdirectory, then aggregate through one summary/validator. A worker's intermediate judgment must never directly become competition evidence. For reusable file-level batches, prefer `run-batch-profile` to pin the inputs; when debugging the expanded flow, use `plan-source-file` to generate a plan, then `run-plan --mode deterministic --execute-merge --auto-retry --max-workers <N>` to execute planned workers with LangGraph-style fan-out/fan-in, retry failed workers through persisted repair hints, and run the final worker-summary aggregation. This is deterministic batch orchestration around the final runner/validator, not a replacement for it. A profile may set `emit_route_governance_metrics_report=true` to also write and bind `summary/route-governance-metrics-report.json` for public-claim boundaries and capability/refusal metrics, not as a semantic gate. If any planned worker lacks a recorded summary after the bounded retry path, final merge execution is skipped fail-closed.

## OpenCode Harness Multi-Agent + SQLite Flow

P0 uses `target/competition-out/state/opencode-agent-harness.sqlite3` as the OpenCode run ledger, worker assignment store, lease store, and artifact index. SQLite is only for recovery, deduplication, leases, and audit indexing. Semantic acceptance still comes only from on-disk evidence and validators.

Typical flow:

```bash
# Preferred reusable profile path:
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json \
  --run-id <run-id> \
  --out-root target/competition-out

# Expanded debugging path:
python3 -B -m validation.tools.opencode_agent_harness init-run \
  --run-id <run-id> \
  --proof-class <proof-class> \
  --out-root target/competition-out

# Preferred file-level batch path:
python3 -B -m validation.tools.opencode_agent_harness plan-source-file \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --target-id <target> \
  --source-repo-root <repo-relative-c-source-root> \
  --source-file <repo-relative-c-file> \
  --function <function> \
  --source-commit <commit> \
  --slice-spec <repo-relative-maintained-slice-spec> \
  --reuse-accepted-evidence \
  --accepted-evidence-root validation/evidence \
  --slice-id-prefix <slice-prefix> \
  --worker-prefix worker \
  --out-root target/competition-out

python3 -B -m validation.tools.opencode_agent_harness run-plan \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --plan target/competition-out/harness/plans/<target>-<source-stem>-workers.json \
  --proof-class <proof-class> \
  --mode deterministic \
  --execute-merge \
  --auto-retry \
  --max-workers 4 \
  --out-root target/competition-out

# Manual expanded single-worker path:
python3 -B -m validation.tools.opencode_agent_harness assign-slice \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --target-id <target> \
  --slice-id <slice> \
  --source-repo-root <repo-relative-c-source-root> \
  --source-file <repo-relative-c-file> \
  --function <function> \
  --source-commit <commit> \
  --compiler-command-source compile_commands.json \
  --include-path include \
  --define DEMO=1 \
  --out-root target/competition-out/workers/worker-a

# For committed accepted evidence reuse, add:
#   --slice-spec <repo-relative-maintained-slice-spec>
#   --reuse-accepted-evidence
#   --accepted-evidence-root validation/evidence

python3 -B -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --mode deterministic

# When local OpenCode / GLM 5.1 is connected, verify exact-command preflight first:
python3 -B -m validation.tools.opencode_agent_harness opencode-preflight \
  --run-id <run-id> \
  --out-root target/opencode-preflight \
  --opencode-model GLM-5.1 \
  --opencode-agent c2rust-migrator \
  --opencode-variant max \
  --opencode-skip-permissions

# Use the agent wrapper only after preflight passes:
python3 -B -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --mode opencode \
  --opencode-model GLM-5.1 \
  --opencode-agent c2rust-migrator \
  --opencode-variant max \
  --opencode-skip-permissions \
  --opencode-preflight-report target/opencode-preflight/harness/opencode-preflight-report.json

`opencode-preflight` only verifies that OpenCode can make its first shell/bash/powershell/cmd tool call exactly match the harness-specified command and write the marker/report; it is not semantic acceptance. The preflight report records the run id, a structured launch policy (`opencode_command`, `opencode_model`, `opencode_agent`, `opencode_variant`, `opencode_skip_permissions`), and the policy hash. `run-worker --mode opencode` and `run-plan --mode opencode` must bind a passed preflight report with `--opencode-preflight-report <report>`, and that report's `run_id` plus launch policy must exactly match the current run and launch flags; otherwise they fail closed before launching OpenCode. `--mode opencode` writes `harness/opencode-handoff-contract.json` and `logs/opencode-session-evidence.json` under the isolated worker directory, then binds both from `harness/run-worker-report.json`, the SQLite event stream, the repair hint, and the artifact index. The contract records the exact deterministic worker command, request, expected summary, OpenCode prompt, and launch policy; the session evidence parses OpenCode `--format json` JSON/JSONL output and keeps a raw fallback when parsing fails. If OpenCode exits with `database is locked` before the first shell command, the launcher performs bounded startup retries and records `opencode_process_retries`; it still requires contract execution and the expected summary before acceptance. These artifacts prove the agent audit chain only; they do not replace `competition-run-summary.json`, the final gate, or validators.

OpenCode safety-transform attempt artifacts are audit evidence only. A publishable `opencode-safety-transform-attempt` must bind hash-bound `handoff_contract`, hash-bound `opencode_session_evidence`, and `contract_verification`; the handoff launch policy must be `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`, and validators must recompute `contract_verification` from the session before accepting the attempt provenance. Missing session evidence, hash drift, non-GLM model, wrong OpenCode agent, command drift, runtime-env drift, or worker-summary drift fails closed. Chat output is never semantic evidence.

The OpenCode preflight launcher and worker launcher use a repo-local runtime env: `opencode-runtime/<scope>/{config,data,cache,tmp}`. Public artifacts record only the repo-relative `opencode_runtime_env`, `env_sha256`, and isolation status, not the full inherited environment. This field audits runtime isolation only; it is not a semantic gate.

`run-plan --auto-retry` is the bounded self-healing path: a failed worker writes a repair hint, the harness retries that same worker, and the loop stops when the worker revalidates or reaches the `REPAIR_ROUND_CAP=5` limit. `--max-workers` controls parallel worker fan-out; the report preserves planner-order fan-in through `run_plan.graph.parallel_map.result_order=planner_order`. Retry success still only means the worker summary revalidated; semantic acceptance remains the final summary validator plus oracle/diff/unsafe gates.

python3 -B -m validation.tools.opencode_agent_harness write-merge-plan \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --proof-class <proof-class> \
  --out-root target/competition-out
```

`write-merge-plan` writes `target/competition-out/harness/merge-plan.json`, which is only a `run_competition.py --worker-summary ...` command plan. The final runner command from that merge plan must still run, and the aggregate summary must still pass `validate_competition_run_summary.py`.

## OpenCode Single-Interaction Prompt Template

```
You are a C-to-Rust automatic translation agent. Your working directory is the root of this repository.

Run the environment check first, then process real C slices. Independent slices may run in parallel, but every worker must use an isolated output directory and isolated OpenCode runtime env; final validation and summary checks must converge through the common gates.

1. source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh
   — Verify the environment meets the competition baseline; `env.sh` activates `CARGO_HOME=config/competition-env/cargo`, and when `toolchain-check.sh` finds clang it also validates resource-dir plus a minimal TU AST dump including `stdint.h`/`stddef.h`.

2. Use direct runner arguments for a single real C source function, or prepare `target/competition-out/extract-specs/<id>-<slice>.json` with at least `repo_root`, `source_file`, `function`, `target_id`, and `slice_id`; optionally include `source_repository`, `source_branch`, `source_commit`, `require_source_commit`, `compiler_command_source`, `include_paths`, and `defines`. `source_file` must be relative to `repo_root`. FlashDB competition-scoring input must bind `https://gitcode.com/xwxf/FlashDB.git`, the `competition` branch, and `f9d0421315c564fb890a1b14eee77b290e0d7bbe`.
   — Direct arguments and JSON extract specs are both parameterized inputs used by the runner to invoke `extract_source_slice.py`; do not hand-write `c_source`.

3. python3 -B validation/tools/run_competition.py --source-repo-root <C_REPO> --source-file <file> --function <name> --target-id <id> --slice-id <slice> --source-repository https://gitcode.com/xwxf/FlashDB.git --source-branch competition --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --compiler-command-source compile_commands.json --include-path include --define DEMO=1 --out-root target/competition-out --proof-class <competition-exact|ci-approximation|wsl-local-simulation|local-simulation>
   — Use the unified runner for slice extraction, environment checks, typed-IR migration, evidence validation, unsafe, OpenSpec, and `competition-run-summary.json` generation; the runner writes generated slice specs under `target/competition-out/slice-specs/`.
   — For batch or reusable inputs, use `--extract-spec target/competition-out/extract-specs/<id>-<slice>.json` instead of the direct source arguments.
   — If independent workers have already produced summaries, pass each one with repeated `--worker-summary target/competition-out/workers/<worker>/summary/competition-run-summary.json`; the aggregate runner does not reprocess those slices, merges their counts, and fails the final gate when any worker is failed or blocked.

4. python3 -B validation/tools/extract_source_slice.py --repo-root <C_REPO> --source-file <file> --function <name> --target-id <id> --slice-id <slice> --source-repository https://gitcode.com/xwxf/FlashDB.git --source-branch competition --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --compiler-command-source compile_commands.json --out target/competition-out/slice-specs/<id>-<slice>.json
   — Manual expanded real C source function slice extraction. When using runner `--extract-spec`, the runner invokes this step.

5. python3 -B validation/tools/auto_migrate.py --slice-spec target/competition-out/slice-specs/<id>-<slice>.json --out-root target/competition-out/evidence --competition-clang-lane
   — Manual expanded full auto-translation pipeline: clang AST → typed IR → Rust draft → C oracle → Rust replay → diff → route/profile. When using the runner, this step is called by the runner.

6. python3 -B validation/tools/validate_auto_translation_evidence.py --target-id <id> --slice-id <slice> --slice-spec target/competition-out/slice-specs/<id>-<slice>.json --evidence-root target/competition-out/evidence --require-semantic-pass
   — Manual expanded full evidence validation. When using the runner, this step is called by the runner.

7. openspec validate --all --strict
   — Manual expanded OpenSpec validation. When using the runner, this step is called by the runner.

8. To improve coverage and accuracy, repeat steps 2-3 for additional real C source functions. Independent slices may run in parallel, but the final aggregate must be merged by the unified runner with `--worker-summary` and pass the same summary validator.

9. For multi-agent parallelism, prefer recording reusable inputs under `config/competition-env/planned-batches/*.json`, then use `run-batch-profile` to create the ledger, generate ordered assignments, execute planned workers with `max_workers`, run bounded `auto_retry=true`, and run the final worker-summary aggregation in one audited command. For debugging, expand it into `init-run`, `plan-source-file`, and `run-plan --mode deterministic --execute-merge --auto-retry --max-workers <N>`. When the profile sets `emit_route_governance_metrics_report=true`, the batch also writes and binds `summary/route-governance-metrics-report.json`. Manual `assign-slice` plus repeated `run-worker --mode deterministic` plus `write-merge-plan` remains the lower-level expanded form. Run `opencode-preflight` first with the same `run_id` to prove OpenCode follows the exact-command contract; use `run-worker --mode opencode --opencode-model GLM-5.1 --opencode-agent c2rust-migrator --opencode-variant max --opencode-preflight-report <report>` or `run-plan --mode opencode --opencode-model GLM-5.1 --opencode-agent c2rust-migrator --opencode-variant max --opencode-preflight-report <report>` only after preflight passes and only when OpenCode wraps assigned requests. Preflight reports from older runs cannot be reused. Worker summaries still converge through the final runner and common summary validator; missing planned worker summaries after up to 5 repair retries skip final merge fail-closed, while OpenCode startup database-lock retries are separately recorded as `opencode_process_retries`.

If the evaluator sets a 600-minute cap, treat it as an external budget; if no cap exists, still do not loosen evidence gates. Current state and next steps come only from `docs/c2rust-migration-agent/future-vision-and-mvp.md`; standalone handoff files must not be treated as judge entrypoints or evidence sources.
Only use the Bash/Shell tool to execute commands. Do not use Write/Edit tools to modify project source code.
If a command fails outside the harness retry path, record the reason and do not enter a manual or unbounded repair loop.
```

## Agent Behavioral Constraints

- **Do not modify project Rust/Python source code** (unless `blocked_repairs` evidence already exists and the original text explicitly allows repair).
- **Do not generate hand-written `c_source` strings** (must extract from real C source files via `extract_source_slice.py`).
- **Do not initiate uncontrolled LLM code generation**. The competition agent may only execute harness-assigned commands or bounded safety-transform attempts through the `OpenCode + GLM-5.1 + c2rust-migrator + max` wrapper; chat output, hand-written source, other models, or candidates that bypass validators cannot enter semantic evidence.
- **Parallel subagents/batch workers are allowed** only for independent slices. Outputs must be isolated, worker status must be recorded, and acceptance must converge through the common validator/final verification. Planned batch execution may preserve planner order in the report/merge input, but it cannot replace the final validator.
- **SQLite is only a harness ledger** for assignment, lease, artifact index, and merge plans; SQLite state cannot replace evidence validation.
- **Prefer `run_competition.py` direct source arguments or `--extract-spec` for real C slice extraction, migration, and aggregation**; `--slice-spec` remains available for already-extracted specs, and isolated worker results enter the same summary validator through repeated `--worker-summary`.
- **If C2Rust baseline generation fails or is absent, record `skipped` or `blocked`**, never fake `generated`.
- **All evidence files must be written to disk**; the validator reads disk files directly, not in-memory constructs.

## Fault Tolerance

| Failure Scenario | Handling |
|------------------|----------|
| `CLANG_PATH` not set and no vendored clang | Write `missing_clang_path`; typed IR lane unavailable. The legacy string translator may only be used as an explicit diagnostic/demo path and must not count as L3 semantic pass. |
| Vendored clang exists but resource-dir or the `stdint.h`/`stddef.h` minimal TU smoke fails | Record clang lane unavailable or blocked; do not treat that clang as an available typed-IR frontend. |
| Huawei Cargo mirror is not activated through `CARGO_HOME=config/competition-env/cargo` | Record mirror activation failure; the existence of `cargo/config.toml` alone is not proof that the competition environment is adapted. |
| C oracle harness compilation failure | Write `compiler_not_found` or specific compile error. Never fake `C_ORACLE_GENERATED`. |
| Rust replay output mismatch with C oracle | Write diff failure evidence. Never fake `passed`. |
| Negative diff does not catch mismatch | Write negative diff failure evidence. Never fake `caught_mismatch`. |
| Validator `--require-semantic-pass` failure | Record the specific failing gate. Do not hand-edit evidence. |

## Competition Output Requirements

Under `target/competition-out/`:

```
target/competition-out/
├── state/
│   └── opencode-agent-harness.sqlite3
├── harness/
│   ├── assignments/<worker-id>.json
│   ├── assignments/<worker-id>-request.json
│   └── merge-plan.json
├── workers/<worker-id>/
│   ├── evidence/
│   ├── summary/competition-run-summary.json
│   └── logs/commands.jsonl
├── evidence/<target>/auto-translation/<slice>/
│   ├── l3-<slice>-clang-lowering-report.json
│   ├── l3-<slice>-rust-draft.rs
│   ├── l3-<slice>-rust-check.json
│   ├── l3-<slice>-c-oracle-status.json
│   ├── l3-<slice>-c-oracle-harness-draft.c
│   ├── l3-<slice>-rust-report.json
│   ├── l3-<slice>-diff.json
│   ├── l3-<slice>-negative-diff.json
│   ├── l3-<slice>-route-decision.json
│   ├── l3-<slice>-validation-profile.json
│   ├── l3-<slice>-auto-translation-manifest.json
│   ├── l3-<slice>-auto-cache-metadata.json
│   ├── l3-<slice>-evidence-manifest.json
│   └── l3-<slice>-final-verification.json
├── summary/
│   └── competition-run-summary.json
└── logs/
    └── competition-run.log
```

`competition-run-summary.json` should contain:

```json
{
  "run_id": "<uuid>",
  "proof_class": "competition-exact | ci-approximation | wsl-local-simulation | local-simulation",
  "profile_id": "huawei-competition-ubuntu-24.04",
  "profile_sha256": "<sha256-of-environment.json>",
  "clang_source": "CLANG_PATH | vendored | missing",
  "cargo_mirror_activation": {
    "method": "CARGO_HOME",
    "path": "config/competition-env/cargo"
  },
  "elapsed_seconds": <int>,
  "translator_version": "0.1.0",
  "slices": {
    "attempted": <int>,
    "typed_ir_generated": <int>,
    "compiled": <int>,
    "semantic_pass": <int>,
    "refused": <int>,
    "blocked": <int>,
    "failed": <int>
  },
  "unsafe_budget": {
    "status": "passed | failed",
    "total_first_party_non_test_unsafe": <int>,
    "ratio": <float>
  },
  "artifact_roots": [
    "target/competition-out/evidence",
    "target/competition-out/summary",
    "target/competition-out/logs"
  ],
  "final_gate": {
    "status": "passed | failed | blocked",
    "validator": "validate_auto_translation_evidence.py --require-semantic-pass"
  }
}
```

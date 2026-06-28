# OpenCode Single-Interaction Competition Workflow

Chinese original: `opencode-single-interaction.md`.

## Overview

The competition evaluation model: OpenCode reads this repository and completes the C-to-Rust migration in a **single interaction**. If the evaluator sets a **600-minute (10-hour)** timeout cap, treat it as an external budget reference. This project still optimizes for accuracy first, not for saving time at the cost of validation. No multi-round prompt tuning, no mid-session branch switching, no external human intervention.

## Goal

Complete within one OpenCode session:

```
Input: repository + CONTEXT.md
  ↓ OpenCode single interaction
Output: real C source function → Rust translation + L3 semantic-pass evidence
```

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

**Multi-slice strategy**: the same OpenCode session may process multiple independent slices in parallel. Parallel runs must give each slice/worker an isolated out-root or subdirectory, then aggregate through one summary/validator. A worker's intermediate judgment must never directly become competition evidence.

## OpenCode Single-Interaction Prompt Template

```
You are a C-to-Rust automatic translation agent. Your working directory is the root of this repository.

Run the environment check first, then process real C slices. Independent slices may run in parallel, but every worker must use an isolated output directory; final validation and summary checks must converge through the common gates.

1. source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh
   — Verify the environment meets the competition baseline; `env.sh` activates `CARGO_HOME=config/competition-env/cargo`, and when `toolchain-check.sh` finds clang it also validates resource-dir plus a minimal TU AST dump including `stdint.h`/`stddef.h`.

2. Prepare `target/competition-out/extract-specs/<id>-<slice>.json` with at least `repo_root`, `source_file`, `function`, `target_id`, and `slice_id`; optionally include `source_commit`, `compiler_command_source`, `include_paths`, and `defines`. `source_file` must be relative to `repo_root`.
   — This is the parameterized input used by the runner to invoke `extract_source_slice.py`; do not hand-write `c_source`.

3. python validation/tools/run_competition.py --extract-spec target/competition-out/extract-specs/<id>-<slice>.json --out-root target/competition-out --proof-class <competition-exact|ci-approximation|wsl-local-simulation|local-simulation>
   — Use the unified runner for slice extraction, environment checks, typed-IR migration, evidence validation, unsafe, OpenSpec, and `competition-run-summary.json` generation; the runner writes generated slice specs under `target/competition-out/slice-specs/`.

4. python validation/tools/extract_source_slice.py --repo-root <C_REPO> --source-file <file> --function <name> --target-id <id> --slice-id <slice> --source-commit <hash> --compiler-command-source compile_commands.json --out target/competition-out/slice-specs/<id>-<slice>.json
   — Manual expanded real C source function slice extraction. When using runner `--extract-spec`, the runner invokes this step.

5. python validation/tools/auto_migrate.py --slice-spec target/competition-out/slice-specs/<id>-<slice>.json --out-root target/competition-out/evidence --competition-clang-lane
   — Manual expanded full auto-translation pipeline: clang AST → typed IR → Rust draft → C oracle → Rust replay → diff → route/profile. When using the runner, this step is called by the runner.

6. python validation/tools/validate_auto_translation_evidence.py --target-id <id> --slice-id <slice> --slice-spec target/competition-out/slice-specs/<id>-<slice>.json --evidence-root target/competition-out/evidence --require-semantic-pass
   — Manual expanded full evidence validation. When using the runner, this step is called by the runner.

7. openspec validate --all --strict
   — Manual expanded OpenSpec validation. When using the runner, this step is called by the runner.

8. To improve coverage and accuracy, repeat steps 2-3 for additional real C source functions. Independent slices may run in parallel, but the final aggregate must be validated by the common gates.

If the evaluator sets a 600-minute cap, treat it as an external budget; if no cap exists, still do not loosen evidence gates. Before running, use the read tool to review CONTEXT.md for current state.
Only use the Bash/Shell tool to execute commands. Do not use Write/Edit tools to modify project source code.
If a command fails, record the reason and do not enter a repair loop.
```

## Agent Behavioral Constraints

- **Do not modify project Rust/Python source code** (unless `blocked_repairs` evidence already exists and the original text explicitly allows repair).
- **Do not generate hand-written `c_source` strings** (must extract from real C source files via `extract_source_slice.py`).
- **Do not initiate LLM code generation** (this project translates through clang-lowered typed IR + generic emitter only, not AI/LLM candidate generation).
- **Parallel subagents/batch workers are allowed** only for independent slices. Outputs must be isolated, worker status must be recorded, and acceptance must converge through the common validator/final verification.
- **Prefer `run_competition.py --extract-spec` for real C slice extraction, migration, and aggregation**; `--slice-spec` remains available for already-extracted specs, and full parallel worker status merging remains a later enhancement.
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

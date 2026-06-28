# OpenCode Single-Interaction Competition Workflow

Chinese original: `opencode-single-interaction.md`.

## Overview

The competition evaluation model: OpenCode reads this repository and completes the C-to-Rust migration in a **single interaction**, with a timeout cap of **600 minutes (10 hours)**. No multi-round prompt tuning, no mid-session branch switching, no external human intervention.

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

To complete reliably within 600 minutes, the project architecture follows these principles:

1. **One prompt, full pipeline.** No agent loop, no multi-turn dialogue, no human mid-process decisions.
2. **Sequential execution, not parallel.** Avoid parallel subagent synchronization overhead and inconsistency risks. Verify each stage before proceeding to the next.
3. **Fail-closed, no iterative repair.** When the translator encounters an unsupported C construct, it refuses and records the reason. No LLM repair loop. Only deterministically-passing candidates enter the validation pipeline.
4. **Evidence-driven, not dialogue-driven.** Correctness depends on machine-verifiable evidence (C oracle + Rust replay + diff + negative diff), not on agent conversational skill.

## Pipeline and Time Estimates

Per-slice estimates using `auto_migrate.py` (real C source function, with clang lowering):

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

**Concurrency strategy**: within a single round, 3-5 independent slices (different functions with no mutual dependencies) can run without blocking each other. Total estimate: ~20 min per slice, 5 slices feasible in one round.

## OpenCode Single-Interaction Prompt Template

```
You are a C-to-Rust automatic translation agent. Your working directory is the root of this repository.

Complete the following tasks in order. No extra exploration. No parallelism. Verify each step before continuing.

1. source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh
   — Verify the environment meets the competition baseline.

2. python validation/tools/extract_source_slice.py --repo-root <C_REPO> --source-file <file> --function <name> --target-id <id> --slice-id <slice> --source-commit <hash> --compiler-command-source compile_commands.json --out validation/slice-specs/<id>-<slice>.json
   — Extract a function slice from a real C source file.

3. python validation/tools/auto_migrate.py --slice-spec validation/slice-specs/<id>-<slice>.json --out-root target/competition-out --competition-clang-lane
   — Run the full auto-translation pipeline: clang AST → typed IR → Rust draft → C oracle → Rust replay → diff → route/profile.

4. python validation/tools/validate_auto_translation_evidence.py --target-id <id> --slice-id <slice> --slice-spec validation/slice-specs/<id>-<slice>.json --require-semantic-pass
   — Full evidence validation. Must pass.

5. openspec validate --all --strict
   — Full OpenSpec validation.

6. If time permits, repeat steps 2-4 for additional real C source functions.

Time limit: 600 minutes. Before running, use the read tool to review CONTEXT.md for current state.
Only use the Bash/Shell tool to execute commands. Do not use Write/Edit tools to modify project source code.
If a command fails, record the reason and do not enter a repair loop.
```

## Agent Behavioral Constraints

- **Do not modify project Rust/Python source code** (unless `blocked_repairs` evidence already exists and the original text explicitly allows repair).
- **Do not generate hand-written `c_source` strings** (must extract from real C source files via `extract_source_slice.py`).
- **Do not initiate LLM code generation** (this project translates through clang-lowered typed IR + generic emitter only, not AI/LLM candidate generation).
- **Do not parallelize subagents** (parallelism introduces uncertainty in single-interaction; this project is designed as a sequential reliable pipeline).
- **If C2Rust baseline generation fails or is absent, record `skipped` or `blocked`**, never fake `generated`.
- **All evidence files must be written to disk**; the validator reads disk files directly, not in-memory constructs.

## Fault Tolerance

| Failure Scenario | Handling |
|------------------|----------|
| `CLANG_PATH` not set and no vendored clang | `missing_clang_path`; typed IR lane unavailable. Fall back to string translator (demo slices only). |
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
  "profile_id": "huawei-competition-ubuntu-24.04",
  "profile_sha256": "<sha256-of-environment.json>",
  "elapsed_seconds": <int>,
  "translator_version": "0.1.0",
  "slices": {
    "attempted": <int>,
    "typed_ir_generated": <int>,
    "compiled": <int>,
    "semantic_pass": <int>,
    "failed": <int>
  },
  "unsafe_budget": {
    "total_first_party_non_test_unsafe": <int>,
    "ratio": <float>
  }
}
```

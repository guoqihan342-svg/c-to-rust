# Quickstart

> A minimal reproduction path for the competition environment. This document assumes Linux (Ubuntu 24.04) or WSL. PowerShell/Windows commands are retained as local convenience entrypoints. Externally assessable verification and evidence generation must provide Linux/CI equivalent commands.

Chinese original: `quickstart.md`.

## 1. Environment Prerequisites

The competition baseline environment is defined in `config/competition-env/environment.json`:

| Item | Version |
|------|---------|
| OS | Ubuntu 24.04.4 LTS (noble) |
| Rust | 1.96.0 (stable) |
| Cargo | 1.96.0 |
| Python | 3.12.3 |
| Node | v24.13.0 |
| npm | 11.6.2 |
| GCC | 13.3.0 |
| GNU Make | 4.3 |

**Unavailable tools**: Go, CMake. Default paths must not depend on them.

**Clang**: Not required by default. Clang is opt-in only, available through:

1. Set the `CLANG_PATH` environment variable pointing to a clang binary;
2. Or place a clang-18 binary at `tools/llvm/bin/clang-18` inside the project (recommended vendored approach);

`auto_migrate.py --competition-clang-lane` prefers `CLANG_PATH`, then searches `tools/llvm/bin/clang-18`, `tools/llvm/bin/clang`, `tools/clang/bin/clang`.

**Package mirrors** (the competition host uses Huawei internal mirrors; local development may use public registries):

| Package Manager | Mirror |
|-----------------|--------|
| apt | `http://mirrors.tools.huawei.com/ubuntu` |
| PyPI | `https://mirrors.tools.huawei.com/pypi/simple` |
| npm | `https://mirrors.tools.huawei.com/npm/` |
| Cargo crates.io | `sparse+http://rust.inhuawei.com/crates.io-index/` |

The Huawei Cargo mirror is activated via `CARGO_HOME=config/competition-env/cargo` without mutating the user's global Cargo configuration.

## 2. Clone the Repository

```bash
git clone https://github.com/guoqihan342-svg/c-to-rust.git
cd c-to-rust
```

If working on an existing checkout, ensure you are on the correct branch:

```bash
git checkout codex/flashdb-rust-skeleton
```

## 3. Activate the Competition Environment

```bash
# Linux/WSL/CI entrypoint
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

`env.sh` will:
- Export `CARGO_HOME=config/competition-env/cargo`, activating the Huawei Cargo mirror;
- Auto-detect repo-root vendored clang paths and export `CLANG_PATH` if found;

`toolchain-check.sh` will:
- Check Rust, Cargo, Python, Node, GCC, Make versions;
- If clang is found, also verify `-print-resource-dir` and run a minimum TU AST dump smoke using `stdint.h`/`stddef.h`;

**Windows/PowerShell local entrypoint** (development convenience only, not for external evaluation):

```powershell
# Set environment variables manually
$env:CARGO_HOME = "config/competition-env/cargo"
# Optional: set CLANG_PATH if LLVM is installed
$env:CLANG_PATH = "C:/Program Files/LLVM/bin/clang.exe"
```

## 4. Environment Smoke Verification

Run the minimal environment smoke to quickly verify the baseline is ready:

```bash
# Linux/CI (do not label as competition-exact)
python validation/tools/run_competition_smoke.py --proof-class ci-approximation

# WSL / local Ubuntu
python validation/tools/run_competition_smoke.py --proof-class wsl-local-simulation

# Only enable this on the actual competition host
python validation/tools/run_competition_smoke.py --proof-class competition-exact --confirm-competition-exact
```

The smoke executes:
- Environment checks and toolchain check;
- Automatic validation of committed evidence (`real-fdb-calc-crc32`) with `--require-semantic-pass`;
- Evidence governance scan;
- Translator coverage matrix check;
- Core validation and translator unit tests;

Output goes to `target/competition-smoke/summary/competition-smoke-summary.json`.

## 5. Translate Your First Real C Slice

Use the unified runner `run_competition.py` for end-to-end slice translation:

```bash
python validation/tools/run_competition.py \
  --source-repo-root sources/FlashDB \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-commit 93d175549da579b8abac07bd175ce4c3f9dde829 \
  --compiler-command-source CMakeLists.txt \
  --include-path inc \
  --out-root target/competition-out \
  --proof-class local-simulation
```

The runner automatically performs:
1. Real C source function slice extraction (`extract_source_slice.py`)
2. clang AST dump → typed IR → Rust draft
3. C oracle harness + Rust replay + diff + negative diff
4. Evidence validation (`--require-semantic-pass`)
5. Unsafe budget scan
6. OpenSpec validate
7. `competition-run-summary.json` generation and validation

**Manual step-by-step** (for debugging):

```bash
# Step 1: Extract the slice
python validation/tools/extract_source_slice.py \
  --repo-root sources/FlashDB \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-commit 93d175549da579b8abac07bd175ce4c3f9dde829 \
  --compiler-command-source CMakeLists.txt \
  --out target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json

# Step 2: Run the translation pipeline
python validation/tools/auto_migrate.py \
  --slice-spec target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json \
  --out-root target/competition-out/evidence \
  --competition-clang-lane

# Step 3: Validate evidence
python validation/tools/validate_auto_translation_evidence.py \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --slice-spec target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json \
  --evidence-root target/competition-out/evidence \
  --require-semantic-pass
```

## 6. OpenCode Single Interaction (Competition Main Path)

The competition evaluation requires OpenCode to complete C→Rust migration in a **single interaction**. The prompt template is at `config/competition-env/opencode-single-interaction.md`.

Minimal run (sequential single slice):

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh

python validation/tools/run_competition.py \
  --source-repo-root sources/FlashDB \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-commit 93d175549da579b8abac07bd175ce4c3f9dde829 \
  --compiler-command-source CMakeLists.txt \
  --include-path inc \
  --out-root target/competition-out \
  --proof-class competition-exact
```

## 7. Multi-Agent / Parallel Workers

When multiple independent real C slices need to be processed, use the OpenCode agent harness for distribution:

### 7.1 Initialize the SQLite Ledger

```bash
python -m validation.tools.opencode_agent_harness init-run \
  --run-id run-demo-001 \
  --proof-class local-simulation \
  --out-root target/competition-out
```

### 7.2 Assign a Slice to a Worker

```bash
python -m validation.tools.opencode_agent_harness assign-slice \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --worker-id worker-a \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-repo-root sources/FlashDB \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --source-commit 93d175549da579b8abac07bd175ce4c3f9dde829 \
  --compiler-command-source CMakeLists.txt \
  --include-path inc \
  --include-path tests \
  --reuse-accepted-evidence \
  --accepted-evidence-root validation/evidence \
  --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json \
  --out-root target/competition-out/workers/worker-a
```

When reusing committed accepted evidence, pass the maintained `--slice-spec`; a freshly extracted temporary spec must not impersonate the authoritative spec. The real source metadata is still recorded in the assignment and SQLite ledger.

Repeat for worker-b, worker-c with other independent slices such as `fdb_kv_set`, `fdb_blob_make`, etc.

### 7.3 Run a Worker

```bash
python -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --worker-id worker-a \
  --mode deterministic
```

`run-worker --mode deterministic` invokes the repo-local `scripts/c2rust-migrator.py --phase migrate --input ...` path and automatically performs the former `record-worker-summary` step when `competition-run-summary.json` exists. When local OpenCode / DeepSeek V4 Pro is connected, use the agent wrapper for the same request:

```bash
python -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --worker-id worker-a \
  --mode opencode \
  --opencode-variant max
```

### 7.4 Generate and Execute the Merge Plan

```bash
python -m validation.tools.opencode_agent_harness write-merge-plan \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --proof-class local-simulation \
  --out-root target/competition-out

# Then execute the command from the merge plan (example)
python validation/tools/run_competition.py \
  --worker-summary target/competition-out/workers/worker-a/summary/competition-run-summary.json \
  --worker-summary target/competition-out/workers/worker-b/summary/competition-run-summary.json \
  --out-root target/competition-out \
  --proof-class local-simulation
```

## 8. Proof Classes

All commands require `--proof-class`, determining the trust level of evidence:

| Class | Meaning | When to Use |
|-------|---------|-------------|
| `competition-exact` | Real competition host run | Only on the actual competition machine |
| `ci-approximation` | CI/GitHub Actions near-equivalent | GitHub Actions or other Linux CI |
| `wsl-local-simulation` | WSL approximate simulation | Ubuntu inside WSL |
| `local-simulation` | Local machine simulation | Developer machine (Windows/macOS/other Linux) |

**Never mix classes**: CI results must not be labeled `competition-exact`.

## 9. Output File Structure

After a successful run, `target/competition-out/` contains:

```
target/competition-out/
├── state/
│   └── opencode-agent-harness.sqlite3    # SQLite scheduling ledger (multi-worker mode)
├── harness/
│   ├── assignments/<worker-id>.json
│   ├── assignments/<worker-id>-request.json
│   └── merge-plan.json
├── workers/<worker-id>/                  # Isolated output per worker
│   ├── evidence/
│   ├── summary/competition-run-summary.json
│   ├── harness/run-worker-report.json
│   └── logs/
├── evidence/<target>/auto-translation/<slice>/
│   ├── l3-<slice>-clang-lowering-report.json
│   ├── l3-<slice>-rust-draft.rs
│   ├── l3-<slice>-c-oracle-status.json
│   ├── l3-<slice>-route-decision.json
│   ├── l3-<slice>-validation-profile.json
│   └── ... (more evidence files)
├── summary/
│   └── competition-run-summary.json
└── logs/
    └── commands.jsonl
```

Key fields in `competition-run-summary.json`:

```json
{
  "run_id": "<uuid>",
  "proof_class": "local-simulation",
  "profile_id": "huawei-competition-ubuntu-24.04",
  "clang_source": "CLANG_PATH | vendored | missing",
  "cargo_mirror_activation": {"method": "CARGO_HOME", "path": "config/competition-env/cargo"},
  "slices": {
    "attempted": 1,
    "typed_ir_generated": 1,
    "compiled": 1,
    "semantic_pass": 1,
    "refused": 0,
    "blocked": 0,
    "failed": 0
  },
  "unsafe_budget": {"status": "passed", "total_first_party_non_test_unsafe": 0, "ratio": 0.0},
  "final_gate": {"status": "passed"}
}
```

## 10. Common Failures and Troubleshooting

### 10.1 `CLANG_PATH` Not Set and No Vendored Clang

**Symptom**: `missing_clang_path`, typed IR lane unavailable.

**Resolution**:
- Option A: Install LLVM clang-18, set `export CLANG_PATH=/usr/bin/clang-18`
- Option B: Download clang-18 binary to `tools/llvm/bin/clang-18` (vendored approach)
- Option C: Skip `--competition-clang-lane` and accept typed IR degradation (default paths do not require clang)

### 10.2 Vendored Clang Exists but AST Dump Smoke Fails

**Symptom**: `toolchain-check.sh` reports clang binary found but the minimum TU smoke with `stdint.h`/`stddef.h` fails.

**Cause**: clang cannot locate its resource-dir or standard headers.

**Resolution**:
- Verify the vendored clang is a complete bundle (including `lib/clang/<version>/include/`);
- Run `clang -print-resource-dir` to confirm the path is correct;
- If using an incomplete bundle, additional standard header paths are needed.

### 10.3 Cargo Mirror Not Activated

**Symptom**: Cargo build fails, unable to download crates.

**Resolution**:
```bash
# Ensure env.sh is sourced
source config/competition-env/env.sh
echo $CARGO_HOME  # Should output config/competition-env/cargo
```

If the Huawei mirror is unreachable from your network in local development, skip `env.sh` and use the public crates.io directly.

### 10.4 C Oracle Harness Compilation Failed

**Symptom**: `c-oracle-status.json` reports `compiler_not_found` or a specific compilation error.

**Cause**: Missing C compiler, or incomplete headers/macros for the C source.

**Resolution**:
- Verify GCC is available: `gcc --version`
- Verify `include_paths` and `defines` in the slice spec are correct
- Verify the source code at `source_commit` matches

### 10.5 Rust Replay Output Mismatches C Oracle

**Symptom**: Diff fails, `l3-<slice>-diff.json` reports mismatch.

**Cause**: The generated Rust draft is semantically inconsistent with the C oracle.

**Handling**:
- Check the diff output to identify which output differs
- Check whether the C source uses constructs unsupported by the translator (see `COVERAGE.md`)
- This is normal fail-closed behavior, not a bug. Record as `refused` or `blocked`.

### 10.6 `validate_auto_translation_evidence.py --require-semantic-pass` Fails

**Symptom**: Validator reports gate failure with details in evidence files.

**Resolution**: Troubleshoot by gate type:
- Missing `oracle_boundary_contract` → `auto_migrate.py` did not generate normally
- `semantic_pass=false` → The run failed (possible C oracle or diff failure)
- Profile hash mismatch → Inconsistent profiles between evidence and environment
- Route/profile/report three-way drift → Internal evidence inconsistency

**Do not manually edit evidence**. A failure is a failure.

### 10.7 Final Gate Failed After Worker Merge

**Symptom**: After merging multiple worker summaries, `competition-run-summary.json` has `final_gate.status=failed`.

**Cause**: At least one worker has `final_gate.status=failed` or `blocked` in its summary.

**Handling**:
- Check each worker's summary to locate the failing worker
- Review that worker's logs and evidence
- SQLite is only a scheduling ledger and cannot substitute for on-disk evidence; the final gate only looks at the merged summary

### 10.8 PowerShell Path Separator Issues

**Symptom**: Paths in command arguments are incorrectly parsed on Windows.

**Resolution**: Use forward slashes `/` in PowerShell or properly escape backslashes. Prefer forward slashes for all command-line arguments.

## 11. Verification Command Reference

```bash
# Environment check
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh

# Environment smoke
python validation/tools/run_competition_smoke.py --proof-class local-simulation

# Translate a single slice
python validation/tools/run_competition.py \
  --source-repo-root sources/FlashDB \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb --slice-id real-fdb-calc-crc32 \
  --source-commit 93d175549da579b8abac07bd175ce4c3f9dde829 \
  --include-path inc \
  --out-root target/competition-out \
  --proof-class local-simulation

# Validate existing evidence only
python validation/tools/validate_auto_translation_evidence.py \
  --target-id flashdb --slice-id real-fdb-calc-crc32 \
  --evidence-root target/competition-out/evidence \
  --require-semantic-pass

# Check unsafe
python validation/tools/unsafe_budget.py --max-ratio 0.10

# Check OpenSpec
openspec validate --all --strict

# Run translator unit tests
cargo test --manifest-path crates/c2r-translator/Cargo.toml

# Run core validation unit tests
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence

# Run documentation mirror contract tests
python -B -m unittest validation.tools.test_doc_mirror_contract
```

## 12. Core Boundary Statements

- **Candidate generation ≠ semantic pass**: typed IR, C2Rust, LLMs, and handwritten rules are only candidate sources; semantic pass is decided solely by the C oracle, Rust replay, diff, negative diff, unsafe ledger, and final verification.
- **No-clang default paths do not equal typed-IR success**: Without `CLANG_PATH` or vendored clang, the typed IR lane is unavailable; the legacy string translator is only an explicit diagnostic/demo path and must not be counted as L3 semantic pass.
- **FlashDB is only a use case**: Do not add FlashDB-specific recognizers, templates, or special-case routes. `flashDB_rust` is a handwritten safe implementation / validation baseline, not automatic translation output.
- **SQLite is a scheduling ledger, not semantic evidence**: The final gate only considers on-disk evidence and the validator, not SQLite state.
- **C2Rust baseline with skipped/blocked status does not count as generated/accepted/semantic pass**.
- **Proof classes must not be mixed**: `ci-approximation` results must not be labeled `competition-exact`.
- **Docs must stay bilingual**: New documents must maintain both the Chinese primary (`.md`) and the English mirror (`.en.md`). The Chinese document's first line must match the repository-standard pointer format.

## 13. Next Steps

1. Read `CONTEXT.md` for current project status
2. Read `future-vision-and-mvp.md` for the roadmap and current P0 backlog
3. Read `COVERAGE.md` for current C construct support boundaries
4. Read `opencode-agent-harness-design.md` for multi-agent design
5. Read `config/competition-env/opencode-single-interaction.md` for the competition single-interaction workflow

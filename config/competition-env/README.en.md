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

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
- clang: not required by default; the typed-IR competition lane requires an explicit clang install plus `CLANG_PATH`

## Files

- `environment.json`: machine-readable baseline, mirrors, and adaptation policy.
- `apt/sources.list`: Ubuntu Noble APT mirror configuration.
- `pip/pip.conf`: pip mirror configuration.
- `npm/.npmrc`: npm registry configuration.
- `cargo/config.toml`: Cargo crates.io mirror configuration.
- `rust/rust-toolchain.toml`: Rust `1.96.0` toolchain declaration; it is not active at the repository root by default.
- `env.sh`: shell environment entrypoint for the competition host.
- `toolchain-check.sh`: competition host self-check script.

## Adaptation Rules

- Default build, test, and validation paths must not require Go.
- Default build, test, and validation paths must not require CMake; C/C++ oracle paths should prefer `gcc`, `g++`, and GNU Make.
- Default build, test, and validation paths must not require clang. When the real clang AST dump typed-IR lane is needed, install clang, export `CLANG_PATH`, then use `auto_migrate.py --competition-clang-lane`; that lane must fail clearly if `CLANG_PATH` is missing.
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

The clang typed-IR competition lane is explicit opt-in:

```bash
export CLANG_PATH="$(command -v clang)"
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane
```

Passing only `--emit-clang-lowering-report` remains diagnostic mode; when clang is missing it writes an unavailable report and does not turn the default non-clang lane into a failure.

If package-manager configuration needs to be installed into the user profile, sync the matching files from this directory to each tool's default location. This repository does not mutate global user configuration automatically.

## Relation To validation/

`validation/environment-profiles/huawei-competition-ubuntu-24.04/` is the historical compatibility entrypoint. The new default configuration entrypoint is this directory; validation evidence may retain the old path as a compatibility reference, but new scripts should default to `config/competition-env/environment.json`.

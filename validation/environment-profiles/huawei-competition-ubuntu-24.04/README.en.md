# Huawei Competition Environment Profile

This directory is the historical validation compatibility entrypoint. The new default competition environment configuration lives under `config/competition-env/`; older evidence or scripts that already reference this directory may continue to read the matching files here.

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

## Usage

New scripts default to:

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

For compatibility with the old validation path:

```bash
source validation/environment-profiles/huawei-competition-ubuntu-24.04/env.sh
bash validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh
```

## Adaptation Rules

- Default build and validation paths must not require Go.
- Default build and validation paths must not require CMake; C/C++ oracle paths should prefer `gcc`, `g++`, and GNU Make.
- Rust code must remain compatible with stable Rust `1.96.0` and must not use nightly-only features.
- Python scripts should target Python `3.12.3` / pip `24.0`.
- Node/npm scripts should target Node `v24.13.0` / npm `11.6.2`.
- Newly generated validation evidence should record `profile_id=huawei-competition-ubuntu-24.04` plus the hash of the `environment.json` path actually used.

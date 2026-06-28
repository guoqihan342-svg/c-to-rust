# 比赛环境配置

本目录是比赛/评测环境的独立配置入口。代码、脚本和验证流水线都应按这里的约束适配；不要把本机 Windows 工具链、历史 evidence 或 validation 兼容目录里的版本当作新的事实来源。

## 环境基线

- OS：Ubuntu 24.04.4 LTS (Noble Numbat)
- Kernel：`5.10.0-182.0.0.95.r194_123.hce2.x86_64`
- APT 镜像源：`http://mirrors.tools.huawei.com/ubuntu`
- Python：`3.12.3`
- pip：`24.0`
- PyPI 镜像源：`https://mirrors.tools.huawei.com/pypi/simple`
- Node.js：`v24.13.0`
- npm：`11.6.2`
- npm registry：`https://mirrors.tools.huawei.com/npm/`
- Java：OpenJDK `21.0.10` (`bisheng_jdk_enterprise`)
- Maven：`3.9.11`
- `MAVEN_HOME`：`/usr/local/maven3`
- Rust：`1.96.0`
- Cargo：`1.96.0`
- Cargo registry：`sparse+http://rust.inhuawei.com/crates.io-index/`
- Go：未安装
- gcc：`13.3.0`
- g++：`13.3.0`
- GNU Make：`4.3`
- CMake：未找到
- clang：默认不要求；typed IR 比赛路线需要显式安装并设置 `CLANG_PATH`

## 文件说明

- `environment.json`：机器可读环境基线、镜像源和适配策略。
- `apt/sources.list`：Ubuntu Noble APT 镜像配置。
- `pip/pip.conf`：pip 镜像配置。
- `npm/.npmrc`：npm registry 配置。
- `cargo/config.toml`：Cargo crates.io 镜像配置。
- `rust/rust-toolchain.toml`：Rust `1.96.0` 工具链声明，不在仓库根目录自动生效。
- `env.sh`：比赛机 shell 会话环境变量入口。
- `toolchain-check.sh`：比赛机环境自检脚本。

## 适配规则

- 默认构建、测试和验证路径不能依赖 Go。
- 默认构建、测试和验证路径不能依赖 CMake；C/C++ oracle 路径优先使用 `gcc`、`g++` 和 GNU Make。
- 默认构建、测试和验证路径不能依赖 clang。需要真实 clang AST dump typed-IR 路线时，先安装 clang，导出 `CLANG_PATH`，再使用 `auto_migrate.py --competition-clang-lane`；缺少 `CLANG_PATH` 时该 lane 必须清晰失败。
- Rust 代码必须兼容 stable Rust `1.96.0`，不得引入 nightly-only 功能。
- Python 脚本按 Python `3.12.3` / pip `24.0` 适配。
- Node/npm 脚本按 Node `v24.13.0` / npm `11.6.2` 适配。
- 直接依赖必须通过 `environment.json.dependency_admission_policy` 准入。新增 libclang、bindgen、syn、quote、tracing、anyhow 或其他依赖前，必须记录它消除的具体语义风险、生成质量风险或可维护性风险，并证明它不破坏默认 competition profile。
- 新生成的 validation evidence 应记录 `profile_id=huawei-competition-ubuntu-24.04` 和 `environment.json` 哈希。

## 使用方式

在比赛机 shell 中执行：

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

clang typed-IR 比赛路线是显式 opt-in：

```bash
export CLANG_PATH="$(command -v clang)"
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane
```

只传 `--emit-clang-lowering-report` 仍是诊断模式；缺 clang 时会产出 unavailable 报告，不会把默认非 clang lane 改成失败。

如果需要把包管理器配置安装到用户目录，按本目录内对应文件同步到工具默认位置；仓库不会自动修改用户全局配置。

## 与 validation 目录的关系

`validation/environment-profiles/huawei-competition-ubuntu-24.04/` 是历史兼容入口。新的默认配置入口是本目录；验证 evidence 可以保留旧路径作为兼容引用，但新脚本默认应使用 `config/competition-env/environment.json`。

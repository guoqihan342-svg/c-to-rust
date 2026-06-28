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
- clang：默认不要求；typed IR 比赛路线需要显式安装 clang 或使用项目内置的 vendored clang

## 文件说明

- `environment.json`：机器可读环境基线、镜像源和适配策略。
- `apt/sources.list`：Ubuntu Noble APT 镜像配置。
- `pip/pip.conf`：pip 镜像配置。
- `npm/.npmrc`：npm registry 配置。
- `cargo/config.toml`：Cargo crates.io 镜像配置。
- `rust/rust-toolchain.toml`：Rust `1.96.0` 工具链声明，不在仓库根目录自动生效。
- `env.sh`：比赛机 shell 会话环境变量入口（含本地 clang 自动探测）。
- `toolchain-check.sh`：比赛机环境自检脚本。
- `opencode-single-interaction.md` / `.en.md`：OpenCode 单次交互比赛流程指南，包含 prompt 模板、时间预估、Agent 行为约束和容错设计。

## Clang 策略：vendored 本地分发

比赛机默认不装 clang，但项目支持把 clang 二进制放进项目目录用：

```
项目根目录/
├── tools/
│   ├── llvm/bin/clang          # 推荐（Linux）
│   ├── llvm/bin/clang.exe      # 推荐（Windows）
│   ├── clang/bin/clang         # 备选路径
│   └── ...
```

**工作流程**：

1. 从本地已有安装复制 clang 二进制（不含 CMake、libclang 等）到 `tools/llvm/bin/`
2. `env.sh` 会自动探测并加入 `PATH`
3. `auto_migrate.py --competition-clang-lane` 优先用 `CLANG_PATH` 环境变量，其次自动搜索上述本地路径
4. 两者都找不到时才返回 `missing_clang_path`

**设计理由**：clang 只用于 `-ast-dump=json` 输出，不依赖 libclang 共享库或 CMake。把 clang 二进制 vendored 进项目目录，比赛机不需要系统级 LLVM 安装，也不需要 `sudo apt install clang`。这符合"不引入系统级依赖"的适配策略。

## 适配规则

- 默认构建、测试和验证路径不能依赖 Go。
- 默认构建、测试和验证路径不能依赖 CMake；C/C++ oracle 路径优先使用 `gcc`、`g++` 和 GNU Make。
- 默认构建、测试和验证路径不能依赖系统级 clang 安装。typed-IR 路线实际需要 clang 时，优先用 `tools/llvm/bin/clang`（vendored 本地二进制），其次用 `CLANG_PATH` 环境变量。`env.sh` 已包含自动探测逻辑。
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
# 方式一：显式设置 CLANG_PATH
export CLANG_PATH="$(command -v clang)"
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane

# 方式二：使用项目内置 clang（env.sh 已自动探测 tools/llvm/bin/clang）
source config/competition-env/env.sh
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane
```

只传 `--emit-clang-lowering-report` 仍是诊断模式；缺 clang 时会产出 unavailable 报告，不会把默认非 clang lane 改成失败。

如果需要把包管理器配置安装到用户目录，按本目录内对应文件同步到工具默认位置；仓库不会自动修改用户全局配置。

## 与 validation 目录的关系

`validation/environment-profiles/huawei-competition-ubuntu-24.04/` 是历史兼容入口。新的默认配置入口是本目录；验证 evidence 可以保留旧路径作为兼容引用，但新脚本默认应使用 `config/competition-env/environment.json`。

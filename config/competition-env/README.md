英文镜像见 `README.en.md`。

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

## FlashDB 源码 Pin

`environment.json.source_pins.flashdb` 固定比赛打分源码为 `https://gitcode.com/xwxf/FlashDB.git`、`competition` 分支、commit `f9d0421315c564fb890a1b14eee77b290e0d7bbe`，对应检出命令为 `git checkout -b competition f9d0421315c564fb890a1b14eee77b290e0d7bbe`。新的 competition-targeted extraction 必须传 `--source-repository`、`--source-branch` 和 `--require-source-commit`，让 `extract_source_slice.py` 在生成 slice spec 前校验实际 checkout。

## 文件说明

- `environment.json`：机器可读环境基线、镜像源和适配策略。
- `apt/sources.list`：Ubuntu Noble APT 镜像配置。
- `pip/pip.conf`：pip 镜像配置。
- `npm/.npmrc`：npm registry 配置。
- `cargo/config.toml`：Cargo crates.io 镜像配置；`env.sh` 会把 `CARGO_HOME` 指向本目录下的 `cargo/`，让 Cargo 使用该镜像配置而不修改用户全局配置。
- `rust/rust-toolchain.toml`：Rust `1.96.0` 工具链声明，不在仓库根目录自动生效。
- `env.sh`：比赛机 shell 会话环境变量入口（含本地 clang 自动探测）。
- `toolchain-check.sh`：比赛机环境自检脚本。
- `smoke.sh`：Linux/WSL/CI 轻量 smoke 入口，调用 `run_competition_smoke.py` 输出 proof-class 分级摘要。
- `planned-batches/`：可复用 planned batch profile 输入；`run-batch-profile` 会按 profile 调用 `init-run`、`plan-source-file` 和 `run-plan --execute-merge`，在 `auto_retry=true` 时启用 `run-plan --auto-retry`，并用 `max_workers` fan-out 独立 worker。
- `judge-entrypoints/`：评委一键入口目录；`flashdb-harness.json` 绑定 FlashDB before/after demo 与显式多 worker evaluate profile 的命令、预期 artifacts、tracked manifest、source pin policy、H1-H6 test contract 和 claim boundary，但不替代 semantic gate。执行入口命令优先用 `python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id before_after_judge_demo --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json`，它会运行入口并在成功后调用本地 artifact 深校验；可加 `--dry-run` 只输出计划。只校验索引时可用 `python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json` 校验入口索引、hash、proof class、source pin/profile 一致性、claim boundary 和 test contract；本地 target artifacts 已生成时可加 `--require-local-artifacts` 深校验 context-pack、agent-index、judge-evidence-index 与 worker 索引一致性。
- `review-checklists/`：milestone/release review gate 输入目录；`flashdb-harness-internal-review.json` 记录 harness architecture、unsafe ledger、coverage matrix、真实切片证据、公开 claim boundary 和已知拒绝项的人工 review 覆盖。`milestone_release_report.py --review-checklist ...` 会把它作为 release readiness 输入；`judge_demo.py --review-checklist ...` 会在 out-root 下生成 `summary/milestone-review-checklist.json` 副本并由 `harness/judge-evidence-index.json` 绑定原始输入与副本；review checklist 不是 semantic gate。
- `opencode-single-interaction.md` / `.en.md`：OpenCode 单次交互比赛流程指南，包含 prompt 模板、时间预估、Agent 行为约束和容错设计。

## Clang 策略：vendored 本地分发

比赛机默认不装 clang，但项目支持把 clang 二进制放进项目目录用：

```
项目根目录/
├── tools/
│   ├── llvm/bin/clang          # 推荐（Linux）
│   ├── llvm/bin/clang-18       # 推荐（带版本 Linux）
│   ├── llvm/bin/clang.exe      # 推荐（Windows）
│   ├── clang/bin/clang         # 备选路径
│   └── ...
```

**工作流程**：

1. 从本地已有安装复制 clang 二进制（不含 CMake、libclang 等）到 `tools/llvm/bin/`
2. `env.sh` 会自动探测并导出 `CLANG_PATH`
3. `toolchain-check.sh` 若找到 clang，会额外执行 `-print-resource-dir` 和包含 `stdint.h`/`stddef.h` 的最小 TU AST dump smoke，确认 resource-dir、标准头和 include 搜索路径可用
4. `auto_migrate.py --competition-clang-lane` 优先用 `CLANG_PATH` 环境变量，其次自动搜索上述本地路径
5. 两者都找不到时才返回 `missing_clang_path`

需要机器可读证据时，运行独立 verifier：

```bash
python validation/tools/verify_vendored_clang.py \
  --proof-class wsl-local-simulation \
  --out target/competition-smoke/summary/vendored-clang-verification.json
```

该 verifier 会在缺 clang 时写出 `status=missing` / `reason=missing_clang_path`，默认不让非 clang 路线失败；传 `--require-clang` 时缺失会让 final gate 失败。有 clang 时，它会记录 clang 来源、版本、`-print-resource-dir`、`-E -v` include 搜索路径、包含 `stdint.h`/`stddef.h` 的最小 TU AST dump、命令日志和 repo/out-root-relative artifact 路径。

**设计理由**：clang 只用于 `-ast-dump=json` 输出，不依赖 libclang 共享库或 CMake。把 clang 二进制 vendored 进项目目录，比赛机不需要系统级 LLVM 安装，也不需要 `sudo apt install clang`。这符合"不引入系统级依赖"的适配策略。

## 适配规则

- 默认构建、测试和验证路径不能依赖 Go。
- 默认构建、测试和验证路径不能依赖 CMake；C/C++ oracle 路径优先使用 `gcc`、`g++` 和 GNU Make。
- 默认构建、测试和验证路径不能依赖系统级 clang 安装。typed-IR 路线实际需要 clang 时，优先用 `CLANG_PATH` 环境变量；未设置时自动搜索 repo root 下的 `tools/llvm/bin/clang-18`、`tools/llvm/bin/clang` 或 `tools/clang/bin/clang` 这类 vendored 本地二进制。`env.sh` 已包含自动探测逻辑，`toolchain-check.sh` 会在找到 clang 时执行最小 TU smoke。
- Cargo 华为镜像通过 `env.sh` 设置 `CARGO_HOME=config/competition-env/cargo` 激活；不要只检查 `cargo/config.toml` 存在，也不要默认修改用户全局 Cargo 配置。
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

执行 `env.sh` 后，`CARGO_HOME` 会指向 `config/competition-env/cargo`，Cargo 将读取其中的 `config.toml` 使用华为 sparse registry。

轻量 Linux/WSL/CI smoke 入口：

```bash
# CI 使用 ci-approximation；WSL 使用 wsl-local-simulation；普通本机使用 local-simulation。
bash config/competition-env/smoke.sh ci-approximation target/competition-smoke

# 等价 Python 入口，可显式设置 run id。
python validation/tools/run_competition_smoke.py \
  --proof-class ci-approximation \
  --run-id core-ci-smoke \
  --out-root target/competition-smoke
```

评委入口中的 `competition_environment_smoke` 使用同一 runner，但输出到 `target/competition-smoke-flashdb-judge-entrypoint`；`competition-smoke-summary.json` 会声明 `claim_boundary.semantic_gate=false`，只证明环境和轻量 evidence gate，不声明新的 semantic pass。

smoke 会执行环境检查、vendored clang 结构化 verifier、核心已提交 evidence validator、`evidence_governance.py`、`translator_coverage_matrix.py` 和轻量 unittest，并写出 `target/competition-smoke/summary/competition-smoke-summary.json`。该摘要会记录 `execution_environment`、`competition_profile_match`、`environment_deviations`、`clang_source`、`vendored_clang_verification.path`、各 gate 状态和日志路径。非 `competition-exact` proof class 中缺 clang 只会在 `vendored-clang-verification.json` 中标为 `missing_clang_path`；`competition-exact` 会把 vendored clang verifier 作为 required gate。除非在真实比赛机上有外部环境证明，否则不要传 `competition-exact`；该模式默认要求 `--confirm-competition-exact`，避免 CI/WSL/local 结果误标成比赛机精确证明。smoke 不是新 slice 翻译，也不声明新的 semantic pass。

评委一键 harness runner：

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

runner 会先做不要求本地 artifacts 的 entrypoint preflight，通过后才执行入口命令；命令成功后再调用本地 artifact 深校验并写出 readiness report。它只是编排证据，语义接受仍只来自 competition summary、workflow metrics、oracle evidence 和 validators。

可复用 planned batch profile 入口：

```bash
python -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json \
  --run-id flashdb-fdb-utils-local \
  --out-root target/competition-out
```

该 profile 只是把 `init-run`、`plan-source-file`、`run-plan --execute-merge` 固化为一条命令；语义接受仍只看最终 `competition-run-summary.json`、workflow metrics 和 validator。当前 FlashDB profile 复用已提交 accepted evidence binding，明确记录 `generated_draft_semantic_pass=false`，不能解读为重新生成 Rust draft 自身通过 semantic gate。已提交的评委展示 profile 设置 `auto_retry=true` 和 `max_workers=4`；retry 只允许失败 worker 消费已落盘 repair hint 并在 5 轮上限内重试，`max_workers` 是 LangGraph 风格 worker fan-out 和 planner 顺序 fan-in，二者都不能替代 validator。

评委 before/after demo profile：

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json \
  --run-id competition-demo-before-after-exhibit \
  --out-root target/competition-out-demo-before-after-exhibit

python -B validation/tools/validate_competition_run_summary.py \
  --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
```

该 profile 会生成 `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`，并绑定 `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json`。它展示 accepted-evidence before/after artifact、unsafe 3→0、`auto_retry=true` 和 harness 五阶段 contract；`generated_draft_semantic_pass=false`，且不会增加 `translation_coverage_numerator`。

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

`validation/environment-profiles/huawei-competition-ubuntu-24.04/` 现在只是 README-only 历史 redirect。新的默认配置入口是本目录；验证 evidence 可以保留旧路径作为历史引用，但新脚本必须使用 `config/competition-env/environment.json`。

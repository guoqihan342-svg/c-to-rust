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
- `bundle-manifest.json`：比赛配置目录的机器可读归档合同，hash 绑定环境 profile、镜像配置、shell 入口、planned batch profiles、judge entrypoint index、review checklist 和 OpenCode runbook；`validate_judge_entrypoints` 会校验它，但它不是 semantic gate。
- `apt/sources.list`：Ubuntu Noble APT 镜像配置。
- `pip/pip.conf`：pip 镜像配置。
- `npm/.npmrc`：npm registry 配置。
- `cargo/config.toml`：Cargo crates.io 镜像配置；`env.sh` 会把 `CARGO_HOME` 指向本目录下的 `cargo/`，让 Cargo 使用该镜像配置而不修改用户全局配置。
- `rust/rust-toolchain.toml`：Rust `1.96.0` 工具链声明，不在仓库根目录自动生效。
- `env.sh`：比赛机 shell 会话环境变量入口（含本地 clang 自动探测）。
- `toolchain-check.sh`：比赛机环境自检脚本。
- `smoke.sh`：Linux/WSL/CI 轻量 smoke wrapper，调用 `run_competition_smoke.py` 输出 proof-class 分级摘要；需要显式 `run-id` 或 timeout 时直接使用 Python 入口。
- `planned-batches/`：可复用 planned batch profile 输入；`run-batch-profile` 会按 profile 调用 `init-run`、`plan-source-file` 和 `run-plan --execute-merge`，在 `auto_retry=true` 时启用 `run-plan --auto-retry`，并用 `max_workers` fan-out 独立 worker。
- `judge-entrypoints/`：评委一键入口目录；`flashdb-harness.json` 绑定 competition environment smoke、FlashDB before/after demo、显式多 worker evaluate profile 和 OpenCode 多 worker evaluate profile。默认不传 `--entrypoint-id` 时会按配置顺序运行全部入口，并写出带 `summary` 的 `judge-entrypoints-run-report.json`；聚焦 before/after 时再加 `--entrypoint-id before_after_judge_demo`。只校验索引时可用 `python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json` 校验入口索引、hash、proof class、source pin/profile 一致性、配置归档 bundle、OpenCode launch policy、claim boundary 和 test contract；本地 target artifacts 已生成时可加 `--require-local-artifacts` 深校验 smoke summary、vendored-clang verification artifact、context-pack、agent-index、judge-evidence-index、route-governance metrics schema、OpenCode preflight/worker launch policy 与 worker 索引一致性。judge-evidence-index 深校验要求 `harness_architecture.context_pack/agent_index` 显式绑定 expected artifacts 和 `evidence_artifact_refs`，防止架构图展示的上下文/agent 索引与评委索引脱节；artifact JSON portability 扫描还会拒绝 Windows、WSL 和 Linux 本机绝对路径，只有诊断 host metadata 与 merge execution trace 的白名单位置可保留。smoke summary 深校验会把 `profile_id/profile_sha256` 绑定到 `environment_profile`，把 `proof_class/run_id` 绑定到 entrypoint，并拒绝 CI/WSL/Windows 本地证据或带 `proof-class-limiting` deviation 的 summary 标成 `competition-exact`；vendored-clang verification 深校验会把 `status/reason/final_gate/clang_lane_verified` 与 smoke summary 绑定，防止 `missing_clang_path` 被误读成 clang lane verified。全量 runner 成功时还会写出 `target/competition-out-flashdb-judge-entrypoints/summary/judge-milestone-bundle.json`，把 run report、readiness report、post-run expected artifacts、workflow metrics、route-governance metrics、OpenCode runtime、`core_translation_quality`、`harness_architecture_summary`、`claim_scope`、`proof_classes`、`publishability`、`known_gaps`、`must_not_claim` 和 `reproduction_commands` 绑定成外部评估索引；它不是 semantic gate，也不增加 translation coverage numerator。
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
- 默认构建、测试和验证路径不能依赖系统级 clang 安装。typed-IR 路线实际需要 clang 时，`CLANG_PATH` 可以是 `PATH` 上的命令名，也可以是 repo 内路径；未设置时自动搜索 repo root 下的 `tools/llvm/bin/clang-18`、`tools/llvm/bin/clang` 或 `tools/clang/bin/clang` 这类 vendored 本地二进制。带路径分隔符的 `CLANG_PATH` 如果解析到 repo 外，会以 `invalid_clang_path_outside_repo` fail-closed。`env.sh` 已包含自动探测逻辑，`toolchain-check.sh` 会在找到 clang 时执行最小 TU smoke。
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
  --timeout-seconds 600 \
  --out-root target/competition-smoke
```

评委入口中的 `competition_environment_smoke` 使用同一 runner，但输出到 `target/competition-smoke-flashdb-judge-entrypoint`；`competition-smoke-summary.json` 会声明 `claim_boundary.semantic_gate=false`，只证明环境和轻量 evidence gate，不声明新的 semantic pass。`validate_judge_entrypoints --require-local-artifacts` 会校验该 summary 的 `profile_id/profile_sha256/proof_class/run_id` 与 `flashdb-harness.json` 一致，并把 `vendored-clang-verification.json` 的 `status/reason/final_gate/clang_lane_verified` 与 summary 绑定，同时拒绝非 repo-relative 的 `clang.path`、expected artifact path、smoke artifact path、judge-evidence-index 架构区缺失的 context/agent refs、artifact JSON 中的 Windows/WSL/Linux 本机绝对路径，以及 `commands.jsonl.command` 中的本机绝对路径；CI/WSL/Windows 本地运行结果冒充 `competition-exact`、缺失 `COMPETITION_EXACT_HOST=1` exact-host attestation、非 CI 冒充 `ci-approximation`、非 WSL 冒充 `wsl-local-simulation`、缺 clang 却把 clang lane 标成 verified、把本机绝对 clang 路径写进评委 artifact、复用旧 command log，或在 command log 中泄露带空格的宿主 Python 可执行路径，都会 fail-closed。

smoke 会执行环境检查、vendored clang 结构化 verifier、核心已提交 evidence validator、`evidence_governance.py`、`translator_coverage_matrix.py` 和轻量 unittest，并写出 `target/competition-smoke/summary/competition-smoke-summary.json`。该摘要会记录 `execution_environment`、`competition_profile_match`、`environment_deviations`、`clang_source`、`vendored_clang_verification.path`、各 gate 状态和日志路径。Python 入口默认 per-step timeout 为 600 秒；超时会写入 `timeout_policy` 和对应 step，exit code 固定为 124，且必须触发 final gate failure，`validate_judge_entrypoints --require-local-artifacts` 会拒绝缺失或漂移的 timeout policy，拒绝非 repo-relative 或包含 parent traversal 的 expected artifact/smoke artifact path，并读取 `commands.jsonl` 拒绝 command 数组中的本机绝对路径。非 `competition-exact` proof class 中缺 clang 只会在 `vendored-clang-verification.json` 中标为 `missing_clang_path`；带路径分隔符的 `CLANG_PATH` 若解析到 repo 外，会标为 `invalid_clang_path_outside_repo` 并 fail-closed；`competition-exact` 会把 vendored clang verifier 作为 required gate。缺失 required C compiler（如 `gcc`/`g++`）不是普通 proof-class 漂移，summary step 会记录 `failure_class=required_c_compiler_missing` 并 fail-closed。除非在真实比赛机上有外部环境证明，否则不要传 `competition-exact`；该模式默认同时要求 `--confirm-competition-exact` 和 `COMPETITION_EXACT_HOST=1`，且 runner 会拒绝在非 CI 上标记 `ci-approximation`、在非 WSL 上标记 `wsl-local-simulation`。smoke 不是新 slice 翻译，也不声明新的 semantic pass。

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

runner 会先做不要求本地 artifacts 的 entrypoint preflight，通过后才执行入口命令；命令成功后再调用本地 artifact 深校验并写出 readiness report。run report 会内嵌 `competition_config_archive`，把 `config/competition-env` 当前文件快照按 path/sha256 绑定；validator 还会校验 `bundle-manifest.json` 的目录级合同。非 dry-run 成功执行时，它还会在 run report 同目录写出 `judge-milestone-bundle.json`；bundle 会 hash 绑定 run report 和 validator-owned artifact refs，并把 focused run 标记为不可作为外部全量 milestone 发布。该 bundle 的一屏字段包括 `core_translation_quality`、`harness_architecture_summary`、`route_governance_metrics`、`evidence_cost_retention`、proof-class rollup、publishability、unsafe reduction scope、OpenCode evidence policy、known gaps、must-not-claim 列表和复现命令；这些字段只服务评委快速审阅，不扩大语义接受范围。`validation/judge-milestone-bundle.schema.json` 是该公开索引的机器合同：run report 必须声明 `schema_version=1` / `report_kind=judge-entrypoints-run-report`，proof class 以 validator-owned `validation.proof_class_contract` 为准，缺失或冲突时 bundle 会 fail-closed。它只是编排证据，语义接受仍只来自 competition summary、workflow metrics、oracle evidence 和 validators。

可复用 planned batch profile 入口：

```bash
python -m validation.tools.opencode_agent_harness run-batch-profile \
  --profile config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json \
  --run-id flashdb-fdb-utils-local \
  --out-root target/competition-out
```

该 profile 只是把 `init-run`、`plan-source-file` 或显式 `workers[]` 计划、`run-plan --execute-merge` 固化为一条命令；语义接受仍只看最终 `competition-run-summary.json`、workflow metrics 和 validator。当前 FlashDB profile 复用已提交 accepted evidence binding，明确记录 `generated_draft_semantic_pass=false`，不能解读为重新生成 Rust draft 自身通过 semantic gate。before/after、accepted-evidence 和 demo 展示 profile 使用 `auto_retry=true` / `max_workers=4`；显式 multi-worker evaluate 与 OpenCode evaluate profile 使用 `auto_retry=false` / `max_workers=2` 来展示确定性 fan-out/fan-in。retry 只允许失败 worker 消费已落盘 repair hint 并在 5 轮上限内重试，`max_workers` 是 LangGraph 风格 worker fan-out 和 planner 顺序 fan-in，二者都不能替代 validator。

当 profile 启用 `emit_route_governance_metrics_report=true` 时，`run-batch-profile` / `evaluate --profile` 还会绑定 `summary/route-governance-metrics-report.json`；`validation/route-governance-metrics.schema.json` 校验该 report 的 claim boundary、denominators、分离计数、S2 workflow 摘要和 `retention_policy`。该 report 与 `retention_policy` 是公开叙述约束和 artifact 保留合同，不是 semantic gate，也不增加 `translation_coverage_numerator`。

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
# 方式一：通过 PATH 显式设置 CLANG_PATH，不把本机绝对路径写进证据
export CLANG_PATH="clang"
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane

# 方式二：使用项目内置 clang（env.sh 已自动探测 tools/llvm/bin/clang）
source config/competition-env/env.sh
python validation/tools/auto_migrate.py --slice-spec <slice.json> --out-root <out> --competition-clang-lane
```

评委证据或已提交 evidence 不应使用 `CLANG_PATH="$(command -v clang)"`：结构化 verifier 会拒绝解析到 repo 外的 path-like `CLANG_PATH`，并把 repo-local clang 路径在命令日志中归一为相对路径。

只传 `--emit-clang-lowering-report` 仍是诊断模式；缺 clang 时会产出 unavailable 报告，不会把默认非 clang lane 改成失败。

如果需要把包管理器配置安装到用户目录，按本目录内对应文件同步到工具默认位置；仓库不会自动修改用户全局配置。

## 与 validation 目录的关系

`validation/environment-profiles/huawei-competition-ubuntu-24.04/` 现在只是 README-only 历史 redirect。新的默认配置入口是本目录；验证 evidence 可以保留旧路径作为历史引用，但新脚本必须使用 `config/competition-env/environment.json`。

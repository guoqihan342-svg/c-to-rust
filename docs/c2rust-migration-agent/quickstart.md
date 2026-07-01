英文镜像见 `quickstart.en.md`。

# 快速入门

> 面向比赛环境的最小复现路径。本文件假设你在 Linux (Ubuntu 24.04) 或 WSL 工作区，但 PowerShell/Windows 命令也保留为本机便利入口。外部可评估的验证与证据生成必须提供 Linux/CI 等价命令。

## 1. 环境前提

比赛基线环境见 `config/competition-env/environment.json`：

| 项 | 版本 |
|----|------|
| OS | Ubuntu 24.04.4 LTS (noble) |
| Rust | 1.96.0 (stable) |
| Cargo | 1.96.0 |
| Python | 3.12.3 |
| Node | v24.13.0 |
| npm | 11.6.2 |
| GCC | 13.3.0 |
| GNU Make | 4.3 |

**未安装的工具**：Go、CMake。默认路径不得依赖它们。

**Clang**：非默认必需。Clang 只作为 opt-in lane，通过以下方式提供：

1. 设置环境变量 `CLANG_PATH` 指向 clang 二进制；
2. 或将 clang-18 二进制放入项目内 `tools/llvm/bin/clang-18`（推荐 vendored 方式）；

`auto_migrate.py --competition-clang-lane` 会优先使用 `CLANG_PATH`，其次搜索 `tools/llvm/bin/clang-18`、`tools/llvm/bin/clang`、`tools/clang/bin/clang`。

**包镜像**（比赛机使用华为内部镜像；本机开发可用公网源）：

| 包管理器 | 镜像 |
|----------|------|
| apt | `http://mirrors.tools.huawei.com/ubuntu` |
| PyPI | `https://mirrors.tools.huawei.com/pypi/simple` |
| npm | `https://mirrors.tools.huawei.com/npm/` |
| Cargo crates.io | `sparse+http://rust.inhuawei.com/crates.io-index/` |

Cargo 华为镜像通过 `CARGO_HOME=config/competition-env/cargo` 激活，不修改用户全局 Cargo 配置。

## 2. 克隆仓库

```bash
git clone https://github.com/guoqihan342-svg/c-to-rust.git
cd c-to-rust
```

如果需要在已有仓库上工作，确保在正确的分支：

```bash
git checkout codex/agent-harness-flashdb-mvp
```

## 3. 激活比赛环境

```bash
# Linux/WSL/CI 入口
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

`env.sh` 会：
- 导出 `CARGO_HOME=config/competition-env/cargo`，激活华为 Cargo 镜像；
- 自动搜索 repo-root vendored clang 路径，发现后导出 `CLANG_PATH`；

`toolchain-check.sh` 会：
- 检查 Rust、Cargo、Python、Node、GCC、Make 等工具版本；
- 若找到 clang，还会验证 `-print-resource-dir` 并通过包含 `stdint.h`/`stddef.h` 的最小 TU AST dump smoke；

**Windows/PowerShell 本机入口**（仅开发便利，不适用于外部评估）：

```powershell
# 手动设置环境变量
$env:CARGO_HOME = "config/competition-env/cargo"
# 可选：设置 CLANG_PATH（如已安装 LLVM）
$env:CLANG_PATH = "C:/Program Files/LLVM/bin/clang.exe"
```

## 4. 环境 smoke 验证

运行最小环境 smoke，快速验证基线是否就绪：

```bash
# Linux/CI（不标 competition-exact）
python validation/tools/run_competition_smoke.py --proof-class ci-approximation

# WSL/本机 Ubuntu
python validation/tools/run_competition_smoke.py --proof-class wsl-local-simulation

# 仅当在真实比赛机上运行时打开此选项
python validation/tools/run_competition_smoke.py --proof-class competition-exact --confirm-competition-exact
```

smoke 会执行：
- 环境检查和 toolchain check；
- 已提交 evidence (`real-fdb-calc-crc32`) 的自动验证 (`--require-semantic-pass`)；
- evidence governance 扫描；
- translator 覆盖矩阵检查；
- 核心 validation 和 translator 单元测试；

输出见 `target/competition-smoke/summary/competition-smoke-summary.json`。

## 5. 翻译第一个真实 C 切片

使用统一 runner `run_competition.py` 完成端到端 slice 翻译：

```bash
python validation/tools/run_competition.py \
  --source-repo-root sources/FlashDB \
  --source-repository https://gitcode.com/xwxf/FlashDB.git \
  --source-branch competition \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --compiler-command-source CMakeLists.txt \
  --include-path inc \
  --out-root target/competition-out \
  --proof-class local-simulation
```

runner 自动完成：
1. 真实 C 源函数切片抽取 (`extract_source_slice.py`)
2. clang AST dump → typed IR → Rust draft
3. C oracle harness + Rust replay + diff + negative diff
4. evidence 验证 (`--require-semantic-pass`)
5. unsafe budget 扫描
6. OpenSpec validate
7. `competition-run-summary.json` 生成与校验

**手动展开版**（如需逐步调试）：

```bash
# Step 1: 抽取切片
python validation/tools/extract_source_slice.py \
  --repo-root sources/FlashDB \
  --source-repository https://gitcode.com/xwxf/FlashDB.git \
  --source-branch competition \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --compiler-command-source CMakeLists.txt \
  --out target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json

# Step 2: 运行翻译管线
python validation/tools/auto_migrate.py \
  --slice-spec target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json \
  --out-root target/competition-out/evidence \
  --competition-clang-lane

# Step 3: 验证 evidence
python validation/tools/validate_auto_translation_evidence.py \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --slice-spec target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json \
  --evidence-root target/competition-out/evidence \
  --require-semantic-pass
```

## 6. OpenCode 单次交互（比赛主路径）

比赛评测要求 OpenCode 用**一次交互**完成 C→Rust 迁移。单次交互的 prompt 模板见 `config/competition-env/opencode-single-interaction.md`。

最小运行（顺序单 slice）：

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh

python validation/tools/run_competition.py \
  --source-repo-root sources/FlashDB \
  --source-repository https://gitcode.com/xwxf/FlashDB.git \
  --source-branch competition \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --compiler-command-source CMakeLists.txt \
  --include-path inc \
  --out-root target/competition-out \
  --proof-class competition-exact
```

如果要通过 OpenCode worker 包装层执行同一条单次请求，只运行已分配的 worker 一次，并要求它产出 summary：

```bash
python -m validation.tools.opencode_agent_harness opencode-preflight \
  --run-id run-demo-001-opencode-preflight \
  --out-root target/competition-out/opencode-preflight \
  --opencode-variant max \
  --opencode-skip-permissions

python -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --worker-id worker-a \
  --mode opencode \
  --opencode-variant max \
  --opencode-preflight-report target/competition-out/opencode-preflight/harness/opencode-preflight-report.json
```

预期 worker 输出是 `target/competition-out/workers/worker-a/summary/competition-run-summary.json`。缺少 summary 输出就是交互失败，不能算部分成功。

## 7. 多 Agent / 并行 Worker

当需要处理多个互不依赖的真实 C slice 时，可用 OpenCode agent harness 分发：

### 7.1 初始化 SQLite 账本

```bash
python -m validation.tools.opencode_agent_harness init-run \
  --run-id run-demo-001 \
  --proof-class local-simulation \
  --out-root target/competition-out
```

### 7.2 分配 slice 给 worker

```bash
python -m validation.tools.opencode_agent_harness assign-slice \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --worker-id worker-a \
  --target-id flashdb \
  --slice-id real-fdb-calc-crc32 \
  --source-repo-root sources/FlashDB \
  --source-repository https://gitcode.com/xwxf/FlashDB.git \
  --source-branch competition \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --compiler-command-source CMakeLists.txt \
  --include-path inc \
  --include-path tests \
  --out-root target/competition-out/workers/worker-a
```

quickstart 主路径必须在 `target/competition-out` 下生成或验证新输出；已提交的历史 evidence 只作为诊断材料，不是默认 worker 输入。

可以为 worker-b、worker-c 等分配其他独立 slice，如 `fdb_kv_set`、`fdb_blob_make` 等。

### 7.3 运行 worker

```bash
python -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --worker-id worker-a \
  --mode deterministic
```

`run-worker --mode deterministic` 会调用 repo-local `scripts/c2rust-migrator.py --phase migrate --input ...`，并在 `competition-run-summary.json` 存在时自动执行原来的 `record-worker-summary` 入库动作。连接本机 OpenCode / DeepSeek V4 Pro 时，可用 agent 包装层执行同一个 request：

```bash
python -m validation.tools.opencode_agent_harness opencode-preflight \
  --run-id run-demo-001-opencode-preflight \
  --out-root target/competition-out/opencode-preflight \
  --opencode-variant max \
  --opencode-skip-permissions

python -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --worker-id worker-a \
  --mode opencode \
  --opencode-variant max \
  --opencode-preflight-report target/competition-out/opencode-preflight/harness/opencode-preflight-report.json
```

### 7.4 生成合并计划并执行

```bash
python -m validation.tools.opencode_agent_harness write-merge-plan \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id run-demo-001 \
  --proof-class local-simulation \
  --out-root target/competition-out

# 然后执行合并计划中的命令（示例）
python validation/tools/run_competition.py \
  --worker-summary target/competition-out/workers/worker-a/summary/competition-run-summary.json \
  --worker-summary target/competition-out/workers/worker-b/summary/competition-run-summary.json \
  --out-root target/competition-out \
  --proof-class local-simulation
```

## 8. 证明等级 (Proof Class)

所有命令都需要指定 `--proof-class`，决定证据的可信级别：

| 等级 | 含义 | 使用场景 |
|------|------|----------|
| `competition-exact` | 真实比赛机运行 | 仅限比赛评测机 |
| `ci-approximation` | CI/GitHub Actions 近乎等价 | GitHub Actions 等 Linux CI |
| `wsl-local-simulation` | WSL 近似模拟 | WSL 内 Ubuntu |
| `local-simulation` | 本机模拟 | 开发者本机 (Windows/macOS/其他 Linux) |

**严禁跨级混用**：CI 结果不能标为 `competition-exact`。

## 9. 输出文件结构

成功运行后 `target/competition-out/` 结构：

```
target/competition-out/
├── state/
│   └── opencode-agent-harness.sqlite3    # SQLite 调度账本（多 worker 模式）
├── harness/
│   ├── assignments/<worker-id>.json
│   ├── assignments/<worker-id>-request.json
│   └── merge-plan.json
├── workers/<worker-id>/                  # 每个 worker 隔离输出
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
│   └── ... (更多 evidence 文件)
├── summary/
│   └── competition-run-summary.json
└── logs/
    └── commands.jsonl
```

第一条 FlashDB slice 需要检查的具体 artifacts：

- `target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json`
- `target/competition-out/evidence/flashdb/auto-translation/real-fdb-calc-crc32/`
- `target/competition-out/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-diff.json`
- `target/competition-out/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-negative-diff.json`
- `target/competition-out/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-final-verification.json`
- `target/competition-out/summary/competition-run-summary.json`
- `target/competition-out/logs/commands.jsonl`

`competition-run-summary.json` 关键字段：

```json
{
  "schema_version": 1,
  "run_id": "<uuid>",
  "proof_class": "local-simulation",
  "profile_id": "huawei-competition-ubuntu-24.04",
  "profile_sha256": "<64 lowercase hex chars>",
  "clang_source": "CLANG_PATH | vendored | missing",
  "cargo_mirror_activation": {
    "method": "CARGO_HOME",
    "path": "config/competition-env/cargo",
    "config_file": "config/competition-env/cargo/config.toml"
  },
  "elapsed_seconds": 0,
  "translator_version": "<git sha or version>",
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
  "artifact_roots": [
    "target/competition-out/slice-specs",
    "target/competition-out/evidence",
    "target/competition-out/summary",
    "target/competition-out/logs"
  ],
  "final_gate": {
    "status": "passed",
    "validator": "validation/tools/validate_competition_run_summary.py"
  }
}
```

## 10. 常见失败与排查

### 10.1 `CLANG_PATH` 未设置且无 vendored clang

**症状**：`missing_clang_path`，typed IR lane 不可用。

**解决**：
- 方案 A：安装 LLVM clang-18，设置 `export CLANG_PATH=/usr/bin/clang-18`
- 方案 B：下载 clang-18 二进制放到 `tools/llvm/bin/clang-18`（项目 vendored 方式）
- 方案 C：不用 `--competition-clang-lane`，接受 typed IR 降级（默认路径不要求 clang）

### 10.2 Vendored clang 存在但 AST dump smoke 失败

**症状**：`toolchain-check.sh` 报告 clang binary 存在但 `stdint.h`/`stddef.h` 最小 TU smoke 失败。

**原因**：clang 找不到 resource-dir 或标准头文件。

**解决**：
- 确认 vendored clang 是完整 bundle（包含 `lib/clang/<version>/include/` 目录）；
- 运行 `clang -print-resource-dir` 确认路径正确；
- 如果使用非完整 bundle，需要额外提供标准头文件路径。

### 10.3 Cargo 镜像未激活

**症状**：Cargo 构建失败，无法下载 crates。

**解决**：
```bash
# 确保 env.sh 已 source
source config/competition-env/env.sh
echo $CARGO_HOME  # 应输出 config/competition-env/cargo
```

本机开发如果网络中无法访问华为镜像，可以跳过 `env.sh`，直接使用公网 crates.io。

### 10.4 C oracle harness 编译失败

**症状**：`c-oracle-status.json` 报告 `compiler_not_found` 或具体编译错误。

**原因**：缺少 C 编译器，或 C 源码依赖的头文件/宏不完整。

**解决**：
- 确认 GCC 可用：`gcc --version`
- 确认 slice spec 中的 `include_paths` 和 `defines` 正确
- 确认 `source_commit` 对应的源码版本正确

### 10.5 Rust replay 输出与 C oracle 不匹配

**症状**：diff 失败，`l3-<slice>-diff.json` 报告 mismatch。

**原因**：生成的 Rust draft 在语义上与 C oracle 不一致。

**处理**：
- 查看 diff 输出，确认哪个具体输出不同
- 检查 C 源码中是否使用了 translator 不支持的构造（见 `COVERAGE.md`）
- 这种情况属于正常 fail-closed，不是 bug。记录为 `refused` 或 `blocked`

### 10.6 `validate_auto_translation_evidence.py --require-semantic-pass` 失败

**症状**：validator 报告 gate failed，详细信息在 evidence 文件中。

**解决**：按失败 gate 的类型排查：
- 缺少 `oracle_boundary_contract` → `auto_migrate.py` 未正常生成
- `semantic_pass=false` → 运行本身未通过（可能是 C oracle 或 diff 失败）
- profile hash 不匹配 → evidence 和 environment 的 profile 不一致
- route/profile/report 三方漂移 → evidence 内部不一致

**不可手工编辑 evidence**。失败就是失败。

### 10.7 Worker 汇总后 final_gate 失败

**症状**：合并多个 worker summary 后，`competition-run-summary.json` 的 `final_gate.status=failed`。

**原因**：至少一个 worker 的 `competition-run-summary.json` 中 `final_gate.status=failed` 或 `blocked`。

**处理**：
- 检查每个 worker 的 summary，定位失败的 worker
- 查看对应 worker 的 logs 和 evidence
- SQLite 只是调度账本，不能替代落盘 evidence；最终 gate 只看汇总的 summary

### 10.8 PowerShell 路径分隔符问题

**症状**：Windows 下命令参数中的路径被错误解析。

**解决**：在 PowerShell 中使用正斜杠 `/` 或正确转义反斜杠。推荐始终使用正斜杠作为命令行参数。

## 11. 验证命令速查

```bash
# 环境检查
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh

# 环境 smoke
python validation/tools/run_competition_smoke.py --proof-class local-simulation

# 翻译单 slice
python validation/tools/run_competition.py \
  --source-repo-root sources/FlashDB \
  --source-repository https://gitcode.com/xwxf/FlashDB.git \
  --source-branch competition \
  --source-file src/fdb_utils.c \
  --function fdb_calc_crc32 \
  --target-id flashdb --slice-id real-fdb-calc-crc32 \
  --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe \
  --include-path inc \
  --out-root target/competition-out \
  --proof-class local-simulation

# 只验证已有 evidence
python validation/tools/validate_auto_translation_evidence.py \
  --target-id flashdb --slice-id real-fdb-calc-crc32 \
  --evidence-root target/competition-out/evidence \
  --require-semantic-pass

# 检查 unsafe
python validation/tools/unsafe_budget.py --max-ratio 0.10

# 检查 OpenSpec
openspec validate --all --strict

# 运行 translator 单元测试
cargo test --manifest-path crates/c2r-translator/Cargo.toml

# 运行核心 validation 单元测试
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence

# 运行文档镜像合同测试
python -B -m unittest validation.tools.test_doc_mirror_contract
```

## 12. 核心边界声明

- **Candidate generation ≠ semantic pass**：typed IR、C2Rust、LLM 和手写规则都只是候选生成来源；语义通过只由 C oracle、Rust replay、diff、negative diff、unsafe ledger 和 final verification 决定。
- **无 clang 的默认路径不等于 typed-IR 成功**：没有 `CLANG_PATH` 或 vendored clang 时，typed IR lane 不可用，legacy string translator 只能作为显式 diagnostic/demo 路径，不得计入 L3 semantic pass。
- **FlashDB 只是回归用例**：不能写 FlashDB 专用 recognizer、模板或特判路径。`flashDB_rust` 是手写安全实现/验证基线，不是自动翻译产物。
- **SQLite 是调度账本，不是语义证据**：最终 gate 只看落盘 evidence 和 validator，不看 SQLite 中的状态。
- **C2Rust baseline 为 skipped/blocked 时不计入 generated/accepted/semantic pass**。
- **Proof class 不可混用**：`ci-approximation` 的结果不能标为 `competition-exact`。
- **文档要双语同步**：新增文档需同时维护中文主文档（`.md`）和英文镜像（`.en.md`）。中文文档第一行必须是 `英文镜像见 \`<对应文件>.en.md\`。`

## 13. 下一步

1. 按本文第 3-5 节完成环境 smoke 和 `real-fdb-calc-crc32` 最小复现。
2. 阅读 `future-vision-and-mvp.md` 了解路线图和当前 P0 待办。
3. 阅读 `COVERAGE.md` 了解当前 C 构造支持边界。
4. 阅读 `config/competition-env/opencode-single-interaction.md` 了解比赛单次交互流程。
5. 阅读 `opencode-agent-harness-design.md` 了解多 agent 设计。

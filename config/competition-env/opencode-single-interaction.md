英文镜像见 `opencode-single-interaction.en.md`。

# OpenCode 单次交互比赛流程

本文是中文主文档。英文镜像见 `opencode-single-interaction.en.md`。

## 概述

比赛评测方式：OpenCode 读取本仓库，用**一次交互**完成 C→Rust 迁移。若评测方设置 **600 分钟（10 小时）**超时上限，把它视为外部预算参考；本项目的设计目标仍是准确性优先，而不是为了压缩时间牺牲验证。不允许多轮手动调 prompt、不允许中途切分支、不允许外部人工干预。

## 目标

一次 OpenCode 会话内完成：

```
输入: 仓库 + CONTEXT.md
  ↓ OpenCode 单次交互
输出: 真实 C 源函数的 Rust 翻译 + L3 语义通过 evidence
```

输出要求：
- 至少一个真实 C 源函数经 typed IR → Rust draft → C oracle → Rust replay → diff → negative diff → final verification 完整证据链
- 证据由 `validate_auto_translation_evidence.py --require-semantic-pass` 通过
- 所有自动翻译证据绑定 competition environment profile
- First-party non-test `unsafe` 比例可审计（理想情况为 0%）

## 单次交互设计原则

为了在一次交互内尽量提高语义准确性，项目架构按以下原则设计：

1. **一次 prompt，完整管线。** 不需要 agent loop、不需要多轮对话、不需要人类中途决策。
2. **允许并行，但证据收敛必须统一。** 可以用多个 subagent 或 batch worker 处理互不依赖的 slice；每个 worker 必须写入独立输出目录，最终由统一 validator/final verification 汇总，不能让 agent 口头判断直接成为通过依据。
3. **fail-closed，不为了赶时间放宽门禁。** 翻译器遇到不支持的 C 构造直接拒绝并记录原因；只有确定性通过的 candidate 才进验证管线。
4. **证据驱动，不是对话驱动。** 正确性不依赖于 agent 的对话能力，而依赖于 C oracle + Rust replay + diff + negative diff 等 machine-verifiable 证据。

## 路线与参考耗时

以下耗时只用于粗略规划，不是验收条件；比赛和开发都以语义准确性与证据完整性优先。按 `auto_migrate.py` 单 slice 估算（真实 C 源函数，含 clang lowering）：

| 阶段 | 操作 | 预估耗时 |
|------|------|----------|
| 1 | 环境自检 (`env.sh` + `toolchain-check.sh`) | < 1 min |
| 2 | 真实源函数 slice 抽取 (`extract_source_slice.py`) | < 1 min |
| 3 | clang AST dump（含 `-Xclang -ast-dump=json -fsyntax-only`） | < 1 min |
| 4 | typed IR lowering + generic emitter + Rust draft | < 1 min |
| 5 | Rust draft 编译检查 (`rustc` / `cargo check`) | < 2 min |
| 6 | C oracle harness 草稿 + 编译 + 执行 | < 3 min |
| 7 | Rust replay 编译 + 执行 | < 3 min |
| 8 | Schema-aware diff + negative diff | < 2 min |
| 9 | unsafe scan + unsafe ledger | < 1 min |
| 10 | 全量 evidence validation (`--require-semantic-pass`) | < 3 min |
| 11 | OpenSpec validate + ci checks | < 2 min |
| **总计预估** | | **< 20 min / slice** |

对 FlashDB crc32（已通过的案例）：typed IR 候选生成到 validation profile 生成约 5-8 分钟。

**多 slice 策略**：允许同一次 OpenCode 会话中并行处理多个独立 slice。并行时必须给每个 slice/worker 分配独立 out-root 或子目录，最终由同一个 summary/validator 汇总；任一 worker 的中间结论都不能直接成为比赛 evidence。文件级批量优先用 `plan-source-file` 生成 plan，再用 `run-plan --mode deterministic` 顺序执行已规划 worker 并生成 merge plan；这只是确定性 batch 调度，不替代最终 runner/validator。

## OpenCode Harness 多 Agent + SQLite 流程

P0 默认使用 `target/competition-out/state/opencode-agent-harness.sqlite3` 作为 OpenCode run ledger、worker assignment、lease 和 artifact index。SQLite 只做恢复、去重、锁租约和审计索引；语义通过仍只看落盘 evidence 和 validator。

典型流程：

```bash
python -m validation.tools.opencode_agent_harness init-run \
  --run-id <run-id> \
  --proof-class <proof-class> \
  --out-root target/competition-out

# 优先的文件级批量路径：
python -m validation.tools.opencode_agent_harness plan-source-file \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --target-id <target> \
  --source-repo-root <repo-relative-c-source-root> \
  --source-file <repo-relative-c-file> \
  --source-commit <commit> \
  --slice-id-prefix <slice-prefix> \
  --worker-prefix worker \
  --out-root target/competition-out

python -m validation.tools.opencode_agent_harness run-plan \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --plan target/competition-out/harness/plans/<target>-<source-stem>-workers.json \
  --proof-class <proof-class> \
  --mode deterministic \
  --out-root target/competition-out

# 手工展开的单 worker 路径：
python -m validation.tools.opencode_agent_harness assign-slice \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --target-id <target> \
  --slice-id <slice> \
  --source-repo-root <repo-relative-c-source-root> \
  --source-file <repo-relative-c-file> \
  --function <function> \
  --source-commit <commit> \
  --compiler-command-source compile_commands.json \
  --include-path include \
  --define DEMO=1 \
  --out-root target/competition-out/workers/worker-a

# 复用已提交 accepted evidence 时额外添加：
#   --slice-spec <repo-relative-maintained-slice-spec>
#   --reuse-accepted-evidence
#   --accepted-evidence-root validation/evidence

python -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --mode deterministic

# 本机连接 OpenCode / DeepSeek V4 Pro 时可改用 agent 包装层：
python -m validation.tools.opencode_agent_harness run-worker \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --mode opencode \
  --opencode-variant max

`--mode opencode` 会在 worker 隔离目录写出 `harness/opencode-handoff-contract.json` 和 `logs/opencode-session-evidence.json`，并由 `harness/run-worker-report.json`、SQLite event、repair hint 和 artifact index 绑定。前者记录 exact deterministic worker command、request、expected summary 和 OpenCode prompt；后者解析 OpenCode `--format json` 的 JSON/JSONL 输出，解析失败时也保留 raw fallback。二者只证明 agent 执行审计链路，不替代 `competition-run-summary.json`、final gate 或 validator。

python -m validation.tools.opencode_agent_harness write-merge-plan \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --proof-class <proof-class> \
  --out-root target/competition-out
```

`write-merge-plan` 生成的 `target/competition-out/harness/merge-plan.json` 只是把 worker summary 汇总为 `run_competition.py --worker-summary ...` 命令。最终仍必须运行 merge plan 中的 runner，并由 `validate_competition_run_summary.py` 校验总 summary。

## OpenCode 单次交互 Prompt 模板

```
你是一个 C-to-Rust 自动翻译 Agent。你的工作目录是当前仓库根目录。

请先完成环境自检，再处理真实 C slice。可以并行处理互不依赖的多个 slice，但每个 worker 必须使用独立输出目录；最终必须统一运行 validator 和 summary 检查。

1. source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh
   — 确认环境满足比赛基线；`env.sh` 会激活 `CARGO_HOME=config/competition-env/cargo`，`toolchain-check.sh` 找到 clang 时会额外验证 resource-dir 和包含 `stdint.h`/`stddef.h` 的最小 TU AST dump。

2. 单个真实 C 源函数优先使用 runner 直接参数；批量或可复用输入可准备 `target/competition-out/extract-specs/<id>-<slice>.json`，至少包含 `repo_root`、`source_file`、`function`、`target_id`、`slice_id`，可选包含 `source_repository`、`source_branch`、`source_commit`、`require_source_commit`、`compiler_command_source`、`include_paths`、`defines`；`source_file` 必须是相对 `repo_root` 的路径。FlashDB 比赛打分源必须绑定 `https://gitcode.com/xwxf/FlashDB.git`、`competition` 分支和 `f9d0421315c564fb890a1b14eee77b290e0d7bbe`。
   — 直接参数和 JSON extract spec 都是 runner 调用 `extract_source_slice.py` 的参数化输入；不要手写 `c_source`。

3. python validation/tools/run_competition.py --source-repo-root <C_REPO> --source-file <file> --function <name> --target-id <id> --slice-id <slice> --source-repository https://gitcode.com/xwxf/FlashDB.git --source-branch competition --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --compiler-command-source compile_commands.json --include-path include --define DEMO=1 --out-root target/competition-out --proof-class <competition-exact|ci-approximation|wsl-local-simulation|local-simulation>
   — 使用统一 runner 执行 slice 抽取、环境检查、typed-IR 迁移、证据验证、unsafe、OpenSpec 和 `competition-run-summary.json` 生成；runner 会把生成的 slice spec 写入 `target/competition-out/slice-specs/`。
   — 批量或可复用输入用 `--extract-spec target/competition-out/extract-specs/<id>-<slice>.json` 替代直接 source 参数。
   — 若多个独立 worker 已分别产出 summary，可用 `--worker-summary target/competition-out/workers/<worker>/summary/competition-run-summary.json` 重复传入汇总；汇总 runner 不会重新处理这些 slice，会合并计数并在任一 worker failed/blocked 时让最终 gate 失败。

4. python validation/tools/extract_source_slice.py --repo-root <C_REPO> --source-file <file> --function <name> --target-id <id> --slice-id <slice> --source-repository https://gitcode.com/xwxf/FlashDB.git --source-branch competition --source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --require-source-commit f9d0421315c564fb890a1b14eee77b290e0d7bbe --compiler-command-source compile_commands.json --out target/competition-out/slice-specs/<id>-<slice>.json
   — 手动展开版的真实 C 源函数切片抽取。使用 runner 的 `--extract-spec` 时该步骤由 runner 调用。

5. python validation/tools/auto_migrate.py --slice-spec target/competition-out/slice-specs/<id>-<slice>.json --out-root target/competition-out/evidence --competition-clang-lane
   — 手动展开版的完整自动翻译管线：clang AST → typed IR → Rust draft → C oracle → Rust replay → diff → route/profile。使用 runner 时该步骤由 runner 调用。

6. python validation/tools/validate_auto_translation_evidence.py --target-id <id> --slice-id <slice> --slice-spec target/competition-out/slice-specs/<id>-<slice>.json --evidence-root target/competition-out/evidence --require-semantic-pass
   — 手动展开版的全量证据验证。使用 runner 时该步骤由 runner 调用。

7. openspec validate --all --strict
   — 手动展开版的 OpenSpec 全量校验。使用 runner 时该步骤由 runner 调用。

8. 为提高覆盖面和准确性，可对额外的真实 C 源函数重复步骤 2-3；互不依赖的 slice 可并行运行，但最终汇总必须用统一 runner + `--worker-summary` 合并并通过同一 summary validator。

9. 如需多 agent 并行，先用 `python -m validation.tools.opencode_agent_harness init-run` 建立 SQLite ledger。文件级批量优先用 `plan-source-file` 生成有序 assignment，再用 `run-plan --mode deterministic` 顺序执行这些 planned workers 并写出 `harness/run-plan-report.json`；手工 `assign-slice` 加重复 `run-worker --mode deterministic` 仍是展开版。只有让 OpenCode 在 exact-command contract 下包装一个 assigned request 时，才使用 `run-worker --mode opencode --opencode-variant max`。worker summary 仍必须通过 `write-merge-plan`、final runner 和 common summary validator 收敛。

若评测方设置 600 分钟上限，将其视为外部预算；没有该限制时也不要降低证据门禁。运行前先用 read 工具看 CONTEXT.md 了解当前状态。
只使用 Shell 工具执行命令，不用 Write/Edit 工具改项目源码。
遇到失败就记录原因，不进入修复循环。
```

## Agent 行为约束

- **不修改项目 Rust/Python 源码**（除非证据目录中已存在 `blocked_repairs` 且原文案明确允许修复）。
- **不生成手写 `c_source` 字符串**（必须从真实 C 源文件通过 `extract_source_slice.py` 抽取）。
- **不启动 LLM code generation**（本项目翻译只走 clang-lowered typed IR + generic emitter，不走 AI/LLM 候选生成）。
- **允许并行 subagent/batch worker**，但只处理互不依赖的 slice；必须隔离输出目录、记录 worker 状态，并由统一 validator/final verification 收敛。planned batch 可以保留 planner 顺序写 report/merge input，但不能替代最终 validator。
- **SQLite 只是 harness ledger**，用于 assignment、lease、artifact index 和 merge plan；不能用 SQLite 中的状态替代 evidence validator。
- **优先使用 `run_competition.py` 直接 source 参数或 `--extract-spec` 做真实 C slice 抽取、迁移和汇总**；`--slice-spec` 仍可用于已经抽取好的 spec，多个隔离 worker 的结果通过重复 `--worker-summary` 进入同一 summary validator。
- **C2Rust baseline 如果生成失败/不存在，记录 `skipped` 或 `blocked`**，不伪造 `generated`。
- **所有 evidence 文件必须落盘**，不可在内存中构造后说 passes——validator 直接读磁盘文件。

## 容错设计

| 失败场景 | 处理方式 |
|----------|----------|
| `CLANG_PATH` 未设置且无 vendored clang | 写 `missing_clang_path`，typed IR lane 不可用；legacy string translator 只能作为显式 diagnostic/demo 路径，不能计入 L3 semantic pass。 |
| vendored clang 存在但 resource-dir 或 `stdint.h`/`stddef.h` 最小 TU smoke 失败 | 记录 clang lane unavailable 或 blocked，不能把该 clang 视为可用 typed-IR 前端。 |
| Cargo 华为镜像未通过 `CARGO_HOME=config/competition-env/cargo` 激活 | 记录 mirror activation failure；不能只用 `cargo/config.toml` 存在证明比赛环境已适配。 |
| C oracle harness 编译失败 | 写 `compiler_not_found` 或具体编译错误。不伪造 `C_ORACLE_GENERATED`。 |
| Rust replay 输出不匹配 C oracle | 写 diff 失败证据。不伪造 `passed`。 |
| negative diff 未检测到错配 | 写 negative diff 失败证据。不伪造 `caught_mismatch`。 |
| validator `--require-semantic-pass` 失败 | 记录具体失败 gate。不手工编辑 evidence。 |

## 比赛输出要求

在 `target/competition-out/` 下生成：

```
target/competition-out/
├── state/
│   └── opencode-agent-harness.sqlite3
├── harness/
│   ├── assignments/<worker-id>.json
│   ├── assignments/<worker-id>-request.json
│   └── merge-plan.json
├── workers/<worker-id>/
│   ├── evidence/
│   ├── summary/competition-run-summary.json
│   └── logs/commands.jsonl
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

`competition-run-summary.json` 应包含：

```json
{
  "run_id": "<uuid>",
  "proof_class": "competition-exact | ci-approximation | wsl-local-simulation | local-simulation",
  "profile_id": "huawei-competition-ubuntu-24.04",
  "profile_sha256": "<sha256-of-environment.json>",
  "clang_source": "CLANG_PATH | vendored | missing",
  "cargo_mirror_activation": {
    "method": "CARGO_HOME",
    "path": "config/competition-env/cargo"
  },
  "elapsed_seconds": <int>,
  "translator_version": "0.1.0",
  "slices": {
    "attempted": <int>,
    "typed_ir_generated": <int>,
    "compiled": <int>,
    "semantic_pass": <int>,
    "refused": <int>,
    "blocked": <int>,
    "failed": <int>
  },
  "unsafe_budget": {
    "status": "passed | failed",
    "total_first_party_non_test_unsafe": <int>,
    "ratio": <float>
  },
  "artifact_roots": [
    "target/competition-out/evidence",
    "target/competition-out/summary",
    "target/competition-out/logs"
  ],
  "final_gate": {
    "status": "passed | failed | blocked",
    "validator": "validate_auto_translation_evidence.py --require-semantic-pass"
  }
}
```

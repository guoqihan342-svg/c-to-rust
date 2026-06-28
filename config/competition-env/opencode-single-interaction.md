# OpenCode 单次交互比赛流程

本文是中文主文档。英文镜像见 `opencode-single-interaction.en.md`。

## 概述

比赛评测方式：OpenCode 读取本仓库，用**一次交互**完成 C→Rust 迁移，超时上限 **600 分钟（10 小时）**。不允许多轮手动调 prompt、不允许中途切分支、不允许外部人工干预。

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

为了在 600 分钟内可靠完成，项目架构按以下原则设计：

1. **一次 prompt，完整管线。** 不需要 agent loop、不需要多轮对话、不需要人类中途决策。
2. **顺序执行，不并行。** 避免并行 subagent 间的同步开销和不一致风险。每个阶段完成后验证结果再进下一阶段。
3. **fail-closed，不迭代修复。** 翻译器遇到不支持的 C 构造直接拒绝并记录原因，不进入 LLM 修复循环。只有确定性通过的 candidate 才进验证管线。
4. **证据驱动，不是对话驱动。** 正确性不依赖于 agent 的对话能力，而依赖于 C oracle + Rust replay + diff + negative diff 等 machine-verifiable 证据。

## 路线与时间预估

按 `auto_migrate.py` 单 slice 估算（真实 C 源函数，含 clang lowering）：

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

**并发策略**：同一轮内可以跑 3-5 个独立 slice（不同函数，互不依赖），每个 slice 不互相阻塞。总预估：单切片约 20 分钟，5 切片可在一轮内完成。

## OpenCode 单次交互 Prompt 模板

```
你是一个 C-to-Rust 自动翻译 Agent。你的工作目录是当前仓库根目录。

请按以下顺序完成任务，不做额外探索，不并行。每一步完成后验证结果再继续。

1. source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh
   — 确认环境满足比赛基线。

2. python validation/tools/extract_source_slice.py --repo-root <C_REPO> --source-file <file> --function <name> --target-id <id> --slice-id <slice> --source-commit <hash> --compiler-command-source compile_commands.json --out validation/slice-specs/<id>-<slice>.json
   — 从真实 C 源文件提取函数切片。

3. python validation/tools/auto_migrate.py --slice-spec validation/slice-specs/<id>-<slice>.json --out-root target/competition-out --competition-clang-lane
   — 运行完整自动翻译管线：clang AST → typed IR → Rust draft → C oracle → Rust replay → diff → route/profile。

4. python validation/tools/validate_auto_translation_evidence.py --target-id <id> --slice-id <slice> --slice-spec validation/slice-specs/<id>-<slice>.json --require-semantic-pass
   — 全量证据验证。必须通过。

5. openspec validate --all --strict
   — OpenSpec 全量校验。

6. 如果时间允许，对额外的真实 C 源函数重复步骤 2-4。

时间限制：600 分钟。运行前先用 read 工具看 CONTEXT.md 了解当前状态。
只使用 Shell 工具执行命令，不用 Write/Edit 工具改项目源码。
遇到失败就记录原因，不进入修复循环。
```

## Agent 行为约束

- **不修改项目 Rust/Python 源码**（除非证据目录中已存在 `blocked_repairs` 且原文案明确允许修复）。
- **不生成手写 `c_source` 字符串**（必须从真实 C 源文件通过 `extract_source_slice.py` 抽取）。
- **不启动 LLM code generation**（本项目翻译只走 clang-lowered typed IR + generic emitter，不走 AI/LLM 候选生成）。
- **不并行 subagent**（并行在单次交互中引入不确定性，本项目设计为顺序可靠管线）。
- **C2Rust baseline 如果生成失败/不存在，记录 `skipped` 或 `blocked`**，不伪造 `generated`。
- **所有 evidence 文件必须落盘**，不可在内存中构造后说 passes——validator 直接读磁盘文件。

## 容错设计

| 失败场景 | 处理方式 |
|----------|----------|
| `CLANG_PATH` 未设置且无 vendored clang | `missing_clang_path`，typed IR lane 不可用。降级到 string translator（仅 demo slice）。 |
| C oracle harness 编译失败 | 写 `compiler_not_found` 或具体编译错误。不伪造 `C_ORACLE_GENERATED`。 |
| Rust replay 输出不匹配 C oracle | 写 diff 失败证据。不伪造 `passed`。 |
| negative diff 未检测到错配 | 写 negative diff 失败证据。不伪造 `caught_mismatch`。 |
| validator `--require-semantic-pass` 失败 | 记录具体失败 gate。不手工编辑 evidence。 |

## 比赛输出要求

在 `target/competition-out/` 下生成：

```
target/competition-out/
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
  "profile_id": "huawei-competition-ubuntu-24.04",
  "profile_sha256": "<sha256-of-environment.json>",
  "elapsed_seconds": <int>,
  "translator_version": "0.1.0",
  "slices": {
    "attempted": <int>,
    "typed_ir_generated": <int>,
    "compiled": <int>,
    "semantic_pass": <int>,
    "failed": <int>
  },
  "unsafe_budget": {
    "total_first_party_non_test_unsafe": <int>,
    "ratio": <float>
  }
}
```

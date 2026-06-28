英文镜像见 `CONTEXT.en.md`。

﻿# CONTEXT.md

本文件是给新 Codex 会话快速接手用的短交接，不是项目路线图、release 文档、能力证明或长会话日志。历史长记录已归档到 `docs/c2rust-migration-agent/archive/context-history-2026-06-28.md`。

## 当前工作区

- 工作目录：`F:\agent\crustpaper\0625ctr`
- 当前分支：`codex/flashdb-rust-skeleton`
- 远端仓库：`https://github.com/guoqihan342-svg/c-to-rust.git`
- 比赛环境默认入口：`config/competition-env/environment.json`
- 当前全局待办唯一来源：`docs/c2rust-migration-agent/future-vision-and-mvp.md`

## 文档入口

- 项目总入口：`README.md`
- C2Rust migration agent 文档目录：`docs/c2rust-migration-agent/README.md`
- 分类索引：`docs/c2rust-migration-agent/index/README.md`
- 当前覆盖边界：`docs/c2rust-migration-agent/COVERAGE.md`
- 核心架构：`docs/c2rust-migration-agent/core-translation-architecture.md`
- 路由与证据门禁：`docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md`

## 待办规则

`docs/c2rust-migration-agent/future-vision-and-mvp.md` 是唯一全局 roadmap/backlog。其他文件的清单只允许作为局部用途：

- `openspec/changes/**/tasks.md`：单个 OpenSpec change 的交付步骤。
- `validation/**/checklist.md`：证据模板的验收 checklist。
- `docs/superpowers/plans/**`：历史实施计划，不再作为当前项目待办来源。
- `validation/evidence/**/*.md`：历史证据记录，不作为当前下一步来源。
- `codex/*.md` 或 `docs/c2rust-migration-agent/analysis/**`：分析材料，不作为 canonical backlog。

## 当前能力边界

- Candidate generation 不等于 semantic pass；typed IR、C2Rust、LLM 和手写规则都只是候选来源。
- FlashDB 只是回归用例，不能恢复 FlashDB/crc32 专用 recognizer、模板或特判路径。
- `flashDB_rust` 是手写安全实现/验证基线，不是自动翻译产物。
- C2Rust baseline 若为 `skipped`、`blocked` 或无 output，不得计入 generated、compiled、accepted 或 semantic pass。
- 无 clang 的默认 CI/比赛路径不能把 legacy string translator 的成功包装成 typed-IR 成功。
- `CONTEXT.md` 只记录接手状态；旧会话段落必须放入 archive，不能继续追加成长日志。

## 常用验证命令

```powershell
git diff --check
openspec validate --all --strict
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo test --manifest-path crates/c2r-translator/Cargo.toml
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
python validation/tools/unsafe_budget.py --max-ratio 0.10
```

## 最近交接

- 2026-06-28：将长 `CONTEXT.md` 归档，根文件收敛为短 handoff。
- 2026-06-28：开始整理文档分类索引，并补核心 translator/validation 注释。
- 保留未跟踪文件：`opencode.json`，除非用户明确要求，不要提交或删除。

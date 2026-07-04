英文镜像见 `CONTEXT.en.md`。

﻿# CONTEXT.md

本文件是给新 Codex 会话快速接手用的短交接，不是项目路线图、release 文档、能力证明或长会话日志。历史长记录已归档到 `docs/c2rust-migration-agent/archive/context-history-2026-06-28.md`。

## 当前工作区

- 工作目录：`F:\agent\crustpaper\0630`
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
- `real-fdb-calc-crc32` 和 `real-fdb-blob-make` 当前通过的是 L4 accepted-evidence authoritative 语义证据绑定；generated Rust draft 仍保持 `generated_draft_semantic_pass=false`。
- `real-fdb-calc-crc32` 的真实 C2Rust baseline 已能生成并 compile-only 通过；direct replay evidence 为 `status=passed` / `observable_replay_pass=true` / `semantic_pass=false`；`verified unsafe baseline` 已通过 `same_output_gate_refs` 把 C oracle/direct replay/diff/negative diff/unsafe/final 绑定到同一 C2Rust output 并 `passed`（P0-C/P0-D0 已关闭），但 OpenCode 证据需在真实 GLM-5.1/OpenCode host 重新生成（P0-H9）。
- `fdb_kv_set` 当前只有 source/signature provenance 和 L4 refused/blocked evidence；external callee shim/model/oracle 语义未关闭。
- OpenCode harness 当前已有 `run-worker --mode deterministic` 最小执行器和 `--mode opencode --opencode-variant max` 包装入口；SQLite 只做调度账本，不能替代落盘 evidence。
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
python -m unittest validation.tools.test_opencode_agent_harness validation.tools.test_run_competition validation.tools.test_c2rust_migrator
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-blob-make --slice-spec validation/slice-specs/flashdb-real-fdb-blob-make.json --require-semantic-pass
python validation/tools/unsafe_budget.py --max-ratio 0.10
```

## 最近交接

- 2026-06-29：在 `codex/agent-harness-flashdb-mvp` 分支同步 docs 到当前 harness/FlashDB MVP 状态：`run-worker`、accepted-evidence 复用、`real-fdb-blob-make` L4 accepted evidence、`fdb_kv_set` blocked callee 边界。
- 2026-07-01：H4 harness 已接入真实 FlashDB `baseline_repair_gate`：`real-fdb-calc-crc32` 第 1 轮产出 baseline unsafe gate 失败证据，root cause 为 `unsafe_baseline_requires_repair`；第 2 轮必须携带 repair hint 并复验 accepted safe evidence。最新验证产物：`target/competition-out-h4-flashdb-context-index-20260701`，其中 `context-pack.json` 和 `agent-index.json` 都索引 `attempt_evidence_policy`。
- 2026-07-02：结合 `opencode-agent-harness-逐行稳定性审查.md` 复核：审查方向有道理，但当前分支已吸收 timeout、atomic write、portable python、retry cap、SQLite lock、fencing audit、`BEGIN IMMEDIATE` 和 POSIX command contract；H7 只保留为回归门禁。待办主线收敛到 P0-C verified unsafe baseline 和 P0-D safety loop。
- `opencode.json` 已是 git 跟踪文件，并进入 CI path filter 与 `config/competition-env/bundle-manifest.json` 归档合同；修改它必须同步 resync hash 绑定。
- 2026-07-04：当前 HEAD `4adbd918`（Bind ledger payloads and worker summary claims to disk evidence），CI 绿。完成外部逐行评审吸收：P0-R1/R2/R9 与 P1-R3/R4/R5/R7 已关闭，详见 `docs/c2rust-migration-agent/future-vision-and-mvp.md` 的「2026-07-04 外部逐行评审吸收与 CI 红灯修复」小节。CI 从连续红灯修复到全绿，根因四类：evidence 哈希级联遗漏、raw/LF 哈希口径分叉、merge gate 依赖未安装的 openspec CLI（127 已豁免）、fresh-checkout 测试状态依赖。legacy 八进制字面量与裸 `char` 已 fail-closed；harness 新增 ledger `payload_json`/`run_id`/`agent_id`/`isolated_out_root` 一致性与 worker `summary_status` 复算防伪。剩余主 blocker 不变：P0-H9（真实 GLM-5.1/OpenCode host）。

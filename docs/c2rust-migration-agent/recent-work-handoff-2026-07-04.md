英文镜像见 `recent-work-handoff-2026-07-04.en.md`。

# 最近开发接力摘要（给其他 Agent）

生成时间：2026-07-04
工作目录：`F:\agent\crustpaper\0630`
当前分支：`codex/flashdb-rust-skeleton`
当前 HEAD：`a070b9437e59a8dbe1e63a6fd8f376bee5176cad`
远端状态：`origin/codex/flashdb-rust-skeleton` 与本地 HEAD 一致
最新 CI：GitHub Actions `Core Translator Validation CI` run `28705610245` 已通过

## 文件边界

这是给其他 AI/Agent 会话接手用的短上下文包。当前用户要求本轮接力信息只写在本文件，英文镜像暂不作为接力入口：

`docs/c2rust-migration-agent/recent-work-handoff-2026-07-04.md`

全局待办只写在：

`docs/c2rust-migration-agent/future-vision-and-mvp.md`

不要再新增其它接力文件、TODO 文件、任务清单文件或临时 roadmap。其它报告、审查材料、聊天导出只能作为参考，不得覆盖上述两个入口。

## 用户硬约束

1. 评委主要看两条轴：核心翻译功能和 harness 架构。当前优先级是先火力全开攻 harness，同时保留能展示核心翻译能力的 before/after 证据链。
2. 比赛正式环境只能用 `OpenCode + GLM-5.1 + c2rust-migrator + max`。现在本机开发先用 `OpenCode + DeepSeek V4 Pro + c2rust-migrator + max` 代替 GLM5.1 进行演练。
3. 本机 DeepSeek、Codex、hostless rehearsal、local simulation 都只能作为开发回归辅助；不能关闭 H9，也不能标成 `competition-exact`。
4. repair 轮数固定为 5 轮；公开证据不得超过 5 轮。
5. 可以开多个 agent / 多个 OpenCode 并行，但只能拆互不共享写入面的任务。不要并行改同一个文件、schema、validator 或 evidence。
6. 测试节奏：开发阶段先跑小模块或单元测试；一个阶段收口后再跑大范围/全项目测试。
7. 评测目标 FlashDB source pin：
   `https://gitcode.com/xwxf/FlashDB`
   `git checkout -B competition f9d0421315c564fb890a1b14eee77b290e0d7bbe`

## 当前工作区状态

最近核对：

```text
git rev-parse HEAD
a070b9437e59a8dbe1e63a6fd8f376bee5176cad

git rev-parse origin/codex/flashdb-rust-skeleton
a070b9437e59a8dbe1e63a6fd8f376bee5176cad
```

旧的未跟踪聊天导出和 7 月 2 日 harness 审查稿已清理；后续 agent 继续只看本文件和 `future-vision-and-mvp.md`。提交前仍要重新看 `git status --short`，确认没有夹带其它 agent 的改动。

## 最近已完成并推送

最新提交：

```text
a070b943 Add DeepSeek OpenCode local rehearsal profile
d528f5e8 Update coverage ledger expectation for blocked callees
82690bb1 Bind refreshed baseline manifests to env profile
cb8aff59 Split typed IR definitions into module
1bb4f44f Close the real-slice evidence refresh item in both mirrors
```

`a070b943` 的重点：

- 新增 DeepSeek 本地演练 profile：`config/competition-env/planned-batches/flashdb-fdb-utils-opencode-deepseek-local-rehearsal.json`。
- harness 默认仍强制 `GLM-5.1`；只有显式 `--opencode-allow-non-competition-model` 才允许非 GLM 本地排练。
- `opencode-preflight` 写入 `non_competition_model_rehearsal` 和 `h9_blocker`，明确本机 DeepSeek 不关闭 H9。
- `verify_opencode_contract_execution()` 对 worker 仍严格要求全 session 只有指定 shell；preflight 只窄口径容忍 marker 文件只读探测。
- 真实本地 run `deepseek-local-rehearsal-20260704d` 已跑通：preflight passed，worker 执行 `scripts/c2rust-migrator.py --phase migrate`，final gate passed，summary validator passed。

本地验证已过：

```text
python -B -m unittest validation.tools.test_opencode_agent_harness -q
python -B -m unittest validation.tools.test_validate_judge_entrypoints -q
python -B -m unittest validation.tools.test_competition_environment_profile validation.tools.test_run_judge_entrypoints -q
python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json
python -B -m validation.tools.validate_competition_run_summary --summary target/competition-out-deepseek-local-rehearsal-20260704d/summary/competition-run-summary.json
git diff --check
```

CI 已全绿：

`https://github.com/guoqihan342-svg/c-to-rust/actions/runs/28705610245`

## 本机 OpenCode 模型状态

最新 `opencode models` 可见 DeepSeek 系列：

```text
opencode/deepseek-v4-flash-free
deepseek/deepseek-chat
deepseek/deepseek-reasoner
deepseek/deepseek-v4-flash
deepseek/deepseek-v4-pro
```

未看到可用于正式关闭 H9 的 `GLM-5.1`。因此当前策略是：

1. 开发演练用 `deepseek/deepseek-v4-pro` + `max`。
2. harness 证据仍必须记录 `local_simulation_closes_p0_h9=false`。
3. 最终必须在真实或等价 `GLM-5.1` OpenCode host 上重跑并刷新 hash-bound artifacts。

注意：普通 `opencode models` 与 harness repo-local isolated runtime 下的 `opencode models` 结果可能不同。切换到 `deepseek/deepseek-v4-pro` 后，必须先跑 focused `opencode-preflight`，不能直接改 profile 后假设可用。

## 当前最小下一步

按 harness-first 继续开发，优先级如下。

### 1. DeepSeek V4 Pro 本地替代路径

目标：把当前 DeepSeek 本地演练从 `opencode/deepseek-v4-flash-free` 升级到 `deepseek/deepseek-v4-pro`，保持 `c2rust-migrator` 和 `max`。

建议顺序：

```text
python -B -m validation.tools.opencode_agent_harness opencode-preflight ^
  --run-id deepseek-v4-pro-preflight-20260704 ^
  --out-root target/competition-out-deepseek-v4-pro-preflight-20260704 ^
  --opencode-model deepseek/deepseek-v4-pro ^
  --opencode-agent c2rust-migrator ^
  --opencode-variant max ^
  --opencode-skip-permissions ^
  --opencode-allow-non-competition-model ^
  --timeout-seconds 360
```

如果 preflight 通过，再改或新增本地演练 profile。不要影响正式 GLM profile。

### 2. OpenCode 多 worker / 多 agent 编排

目标：在 DeepSeek V4 Pro 本地替代模式下跑 2 个独立 FlashDB worker，验证 `context-pack`、`agent-index`、SQLite ledger、worker report、preflight binding、resume manifest 和 merge summary 的一致性。

推荐拆分：

- Agent A：只负责 DeepSeek V4 Pro preflight/profile/CLI 传参。
- Agent B：只负责 context-pack / agent-index / SQLite ledger 一致性负例。
- Agent C：只负责 worker report / handoff contract / session evidence / safety attempt 交叉绑定。
- Agent D：只负责 FlashDB competition source pin / bootstrap / judge entrypoint path。

不要让两个 agent 同时改 `validation/tools/opencode_agent_harness.py` 或 `validation/tools/validate_judge_entrypoints.py`。

### 3. 核心翻译 before/after 展品

目标：在 harness 稳定后，优先做一个评委看得懂的 before/after：

```text
C source slice
raw C2Rust or candidate unsafe Rust
verified unsafe baseline
accepted safe patch
C oracle / Rust replay / schema diff / negative diff
unsafe before/after
workflow-metrics.json
competition-run-summary.json
```

如果短期不能产生新的 safe patch，不要伪造 unsafe reduction；保留 verified unsafe baseline + fail-closed repair trace。

## 测试策略

开发中只跑小测试：

```text
python -B -m unittest validation.tools.test_opencode_agent_harness.OpenCodeAgentHarnessTest.<focused_test> -q
python -B -m unittest validation.tools.test_validate_judge_entrypoints.JudgeEntrypointsValidatorTests.<focused_test> -q
git diff --check
```

阶段收口后再跑：

```text
python -B -m unittest validation.tools.test_opencode_agent_harness -q
python -B -m unittest validation.tools.test_validate_judge_entrypoints -q
python -B -m unittest validation.tools.test_competition_environment_profile validation.tools.test_run_judge_entrypoints -q
python -B -m validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json
```

全部开发完成后再跑全项目/CI 级验证，包括但不限于 FlashDB competition source pin、judge entrypoints、competition smoke、coverage matrix、route governance metrics、unsafe budget 和 GitHub Actions。

## 不要做

1. 不要声称本机 DeepSeek 关闭 H9。
2. 不要把 OpenCode chat/session 文本当 semantic evidence。
3. 不要把 accepted evidence 复用说成新 translator-generated semantic pass。
4. 不要新增其它待办/接力文件。
5. 不要提交其它 agent 正在写的未跟踪报告，除非用户明确要求。
6. 不要并行修改同一个 validator/schema/evidence 文件。
7. 不要为了 clean code 重构偏离 harness 和核心翻译功能主线。

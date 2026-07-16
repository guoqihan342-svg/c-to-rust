# C-to-Rust Competition Runtime

本文件由外层 OpenCode 自动加载。目标是让未知 C 仓库通过本项目的 AI-first harness 完成迁移和项目级验证，而不是让外层模型手工改写若干文件后提前结束。

## 内部任务优先级

当提示中包含 `Task mode: generate-candidate` 或 `Task mode: execute-command` 时，这是 harness 启动的隔离 worker。严格遵守该任务模式和对应 `.opencode/agents/*.md`，不要执行下面的外层流程。

## 外层比赛流程

1. 从用户提示取得目标 C 仓库路径。不要把本 harness 仓库误当成待翻译项目，也不要按项目名、文件名、测试名或已知测试身份选择翻译规则。
2. 优先使用目标仓库已有且唯一的 `compile_commands.json`。若缺失或有多个候选，只依据目标项目自己的构建元数据生成或显式选择 BuildIR 输入；不得猜测编译参数、测试答案或绕过 `required` 构建闭包。
   对 Make 项目，先从项目自己的 Makefile 元数据选择一个字面测试 target，再调用 `prepare-make-test-target-proposal`；把其 JSON 输出中的 `migrate_arguments` 原样追加到下方 `migrate`。AI 只选择 target，不得提供 Make argv、recipe、工作目录、测试答案或权威哈希。若宿主返回 `project_test_make_ai_target_proposal_required`，必须完成这一步，禁止回退到猜测的 `test/check` 或自行执行 `make -n` 冒充测试清单。
3. 从 harness 仓库根执行唯一比赛入口：

```bash
python3 -B validation/tools/project_migration_harness.py migrate \
  --repo-root "$TARGET_C_REPOSITORY" \
  --profile competition \
  --out-root target/project-migration/competition-run \
  --run-id competition-run \
  --build-closure-policy required \
  --logical-model GLM-5.1 \
  --resolved-model zai/glm-5.1
```

4. `migrate` 会执行计划、隔离多 worker 候选/repair、Cargo 重建、原 C 与 Rust 项目测试对照及最终完成门。只有顶层返回 `status=completed` 且 `semantic_gate=true` 才能结束。
5. 若返回 blocked/failed，只读取结构化 `stage`、`reason_code`、`blockers` 和 hash-bound evidence，解决目标项目自身的构建发现或环境问题后，用相同 `out-root`/`run-id` 恢复。不得删除验证器、修改 oracle/expected output、放宽门禁、复制旧 evidence 或把 compile-only 当作成功。
6. 最终交付必须指出生成 Rust workspace 和 completion receipt；任何未完成状态都要如实报告最后阶段和阻塞原因。

## 准确率规则

- AI、typed IR 和 C2Rust 都只产生候选；共同的 host verifier 决定接受、repair 或拒绝。
- 模型不得读取 expected/actual、oracle 输出或隐藏测试答案；修复只消费允许的结构化诊断。
- 不允许针对任何项目名、测试身份、已知路径或固定 fixture 写特判。
- 不允许在 `plan`、`preflight`、`dispatch`、单个 worker 成功、Cargo 编译成功或单个 gate 后停止。

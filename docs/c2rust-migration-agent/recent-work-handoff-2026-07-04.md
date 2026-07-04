英文镜像见 `recent-work-handoff-2026-07-04.en.md`。

# 最近开发接力摘要（给其他 Agent）

生成时间：2026-07-04  
工作目录：`F:\agent\crustpaper\0630`  
当前分支：`codex/flashdb-rust-skeleton`  
当前 HEAD：`69abdb619cf89c723aa675efdcc45180e338aaf5`  
远端状态：`origin/codex/flashdb-rust-skeleton` 与本地 HEAD 一致  
最新 CI：GitHub Actions `Core Translator Validation CI` run `28698387347` 已通过  

## 这份文件的用途

这是一份给其他 AI/Agent 会话接手用的短上下文包。它不是完整逐字聊天记录，而是最近实际开发、验证、提交、推送后的工程状态摘要。接手 Agent 应以当前仓库状态为准，先运行 `git status --short` 和必要的 focused tests，再继续开发。

## 用户硬约束

1. 比赛环境只能使用 `GLM-5.1` 模型。
2. Agent 工具按比赛路径使用 `opencode`，正式证据必须是 `opencode + GLM-5.1 + c2rust-migrator + max`。
3. 本机 Codex、非 GLM OpenCode、hostless rehearsal、local simulation 都只能作为开发回归辅助，不能关闭正式 H9 / `competition-exact` gate。
4. repair 轮数为 5 轮；不要生成超过 5 轮的公开 repair/自愈证据。
5. 评委最看重两条轴：核心翻译功能和 harness 架构；当前策略是优先攻 harness。
6. 使用多 agent / OpenCode 并行时，只能拆独立任务；不要并行改同一个文件、schema 或共享 evidence。
7. 全局待办只维护在：
   - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
   - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
8. 不要把 clean code、无关重构、历史治理清理放到 harness/评测复现之前。

## 当前工作区状态

最新核对时，只有未跟踪文档，没有未提交代码改动：

```text
?? docs/c2rust-migration-agent/chat-export-for-other-ai-2026-07-04.md
?? docs/c2rust-migration-agent/harness-stability-review-2026-07-02.md
?? docs/c2rust-migration-agent/recent-work-handoff-2026-07-04.md
```

前两个文件是既有未跟踪文档；本文件是本次新增的接力摘要。除非用户明确要求，不要把这些未跟踪文档混进功能提交。

## 最近已提交并推送的工作

最近提交序列：

```text
69abdb61 Publish smoke summary atomically
d4933ae6 Fix function pointer parameter qualType parsing
f90476a2 Fail closed misleading clang qualType models
e428e452 Reuse clang lowering report for draft artifacts
d61a0d6f Make real clang smoke tests visibly gated
f910b3af Sync harness backlog with verified closures
```

### `d61a0d6f`：real clang smoke 可见但默认 gated

目的：让 real clang 相关 smoke 测试在测试列表里可见，但默认 ignored，避免本机缺 clang 时误阻塞常规 CI。  
结果：123 个 real clang 测试默认 ignored，并统一走 `real_clang_ast_test_setup()`。

### `e428e452`：draft artifacts 复用 clang lowering report

目的：`write_translation_artifacts()` 不再重复跑 clang lowering，改为复用同一份 report，减少证据漂移和重复成本。  
验证：相关 translator/harness 测试通过，CI 通过。

### `f90476a2` + `d4933ae6`：clang `qualType` 误导模型 fail-closed

内容：
- 多维数组 type 显式 fail-closed，分类为 `invalid_array_type`。
- 函数指针返回类型 fail-closed。
- fixed-width typedef desugared/canonical validation；目标相关 ABI 宽度无法证明时 deferral。
- 修复函数指针参数被误判成函数指针返回的问题：先用 balanced `split_function_qual_type`，只有 split 失败且字符串含 `(*` 时才按 function-pointer return fail-closed。

关键测试：

```text
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features clang_ast_fixture_replays_function_pointer_parameter_call_without_clang -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report function_return_type_from_type_object -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet
cargo fmt --check --manifest-path crates/c2r-translator/Cargo.toml
python -B -m unittest validation.tools.test_doc_mirror_contract -q
git diff --check
```

结果：`d4933ae6` 的 GitHub Actions run `28698112457` 通过。

### `69abdb61`：smoke summary 原子发布

这是最近一刀 harness 稳定性修复。

问题：`validation/tools/run_competition_smoke.py` 之前直接 `write_text()` 写 `summary/competition-smoke-summary.json`。如果进程崩溃或写入失败，评测链可能读到半写 summary 或过期 summary。

改动：
- 新增 `atomic_write_text(path, text)`。
- 写入同目录临时文件：`.competition-smoke-summary.json.<pid>.<time_ns>.tmp`。
- 用 `os.replace(tmp, final)` 原子发布。
- 失败时清理临时文件。
- `run_competition_smoke()` 发布 summary 时改用该 helper。

新增回归测试：

```text
validation.tools.test_run_competition_smoke.RunCompetitionSmokeTests.test_smoke_summary_publication_is_atomic_when_replace_fails
```

TDD 记录：
- 红测：生产代码未改前失败，错误为 `AssertionError: OSError not raised`，说明没有走 `os.replace`。
- 绿测：实现 helper 后该测试通过。

本地 focused 验证：

```text
python -B -m unittest validation.tools.test_run_competition_smoke.RunCompetitionSmokeTests.test_smoke_summary_publication_is_atomic_when_replace_fails -q
python -B -m unittest validation.tools.test_run_competition_smoke validation.tools.test_validate_judge_entrypoints -q
git diff --check
```

结果：

```text
Ran 255 tests in 3.535s
OK
```

远端验证：
- GitHub Actions run `28698387347` 通过。
- 覆盖步骤包括 translator 默认测试、feature matrix、no-clang typed IR fixture replay、core validation Python tests、LF/hash gates、judge entrypoint runner plan、fresh LF clone judge entrypoint preflight、competition CI smoke gate、unsafe budget、coverage matrix、milestone report、route governance metrics 和 diff whitespace。

## 最近讨论过的重要结论

### `flashDB_rust` 是否保留

结论：保留。  
原因：它是 tracked 的手写 safe/reference implementation 和 validation baseline，不是普通自动生成临时产物。删除会削弱对照、验证和展示材料。

### `openspec/` 是否删除

结论：现在不要直接删。  
原因：
- `openspec/` 还有大量 tracked 文件。
- `README.md`、`scripts/run-full-regression.ps1`、competition env 文档和历史 evidence 仍引用 OpenSpec。
- 当前策略是把 OpenSpec 从新开发主路径降级为历史治理/证据归档，而不是立刻删除。

后续如果要退役，必须单独做迁移：
1. README 标注 OpenSpec 是历史归档，不是当前开发入口。
2. full regression 里的 OpenSpec gate 改为可选或移除。
3. competition env 文档移除 OpenSpec required preflight。
4. 确认 judge entrypoints、smoke、public packet 不再依赖 OpenSpec。
5. 最后再考虑删除目录。

### 本机 OpenCode / GLM 状态

之前核对过：本机 `opencode models` 没有可用于关闭 H9 的 `GLM-5.1` 证据。  
因此不要在本机强行启动 OpenCode worker 并把结果当正式 competition evidence。H9 必须在真实 competition GLM/OpenCode host 或等价 provider 配置上重跑并绑定证据。

## 已使用/沉淀的 Agent 信息

最近启动过两个只读分析子任务，结论如下。

### Arendt：legacy translator retirement

发现：
- `translate_slice` 通过 `lib.rs` 和 `legacy_translation.rs` 暴露为 public API。
- CLI 当前主要走 `write_translation_artifacts()`，不是直接依赖 public `translate_slice`。
- artifact 生成已经把 legacy 包成 retired diagnostics，例如 `legacy_direct_retired` / `legacy_fallback_retired`。
- 但 legacy emitter 仍有风险路径：未匹配 pointer funcs 可能发出 `return_code: 0, status: "ok"` shell；out-buffer 模板会把 `out[0]=v` 改写成 `return v`。
- 直接移除 public re-export 会破坏大量 `bounded_translation.rs` 集成测试。

建议：
- 后续若做 P1-R6，先迁移 direct legacy 测试，再移除 `pub use legacy_translation::translate_slice` 或降为 `pub(crate)`。
- 这项比 smoke summary 原子发布大，不应和 H9/competition evidence 抢主路径。

### James：local harness next step

建议优先级：
1. `run_competition_smoke.py` 的 summary 原子发布。已在 `69abdb61` 完成。
2. 加强 `validate_judge_entrypoints.py` 中 context / agent ledger 一致性校验：检查 agent-index artifact row `payload_json`、ledger `run_id`、artifact 绑定是否一致。这项还未做，可作为下一刀 harness hardening。

## 当前真正的剩余 blocker

### P0-H9：competition bootstrap / exact GLM OpenCode contract

仍未关闭。正式关闭需要真实或等价比赛 host 产出：

```text
opencode
GLM-5.1
c2rust-migrator
max
auto_retry=true
repair cap = 5
COMPETITION_EXACT_HOST=1
```

必须有：
- `opencode models` stdout/stderr hash-bound logs。
- exact-token `GLM-5.1` proof。
- passed `opencode-preflight`。
- `handoff_contract`。
- `opencode_session_evidence`。
- marker file。
- worker report / event stream / artifact index 交叉绑定。
- `competition-run-summary.json` 绑定 `workflow-metrics.json`。
- public packet / milestone bundle / release notes 里同一份 preflight proof summary。

本机 local-simulation 或 hostless rehearsal 只能证明 wiring，不关闭 H9。

## 建议下一步

按当前比赛优先级，下一位 Agent 建议从以下顺序继续：

1. **H9 真机/等价 host 路径**：如果能拿到 `GLM-5.1` OpenCode 环境，优先跑 `opencode-preflight`、competition smoke、judge entrypoints，并刷新 hash-bound artifacts。
2. **context / agent ledger 一致性**：在没有真机 GLM 时，继续加 `validate_judge_entrypoints.py` 或 `validate_context_ledger_contract` 负例，防止 agent-index、SQLite ledger、worker report、artifact index 漂移。
3. **OpenCode worker evidence cross-binding**：继续强化 worker summary、handoff contract、session evidence、repair history、workflow metrics 之间的不可伪造绑定。
4. **legacy translator retirement P1-R6**：只有在 harness 主线稳定后再做。不要为了“清理”破坏现有 direct tests。
5. **文档只做必要同步**：如果改 `future-vision-and-mvp.md`，必须同步 `.en.md` 并跑：

```text
python -B -m unittest validation.tools.test_doc_mirror_contract -q
```

## 常用 focused 验证命令

修改 smoke runner 或 judge validator 后：

```text
python -B -m unittest validation.tools.test_run_competition_smoke validation.tools.test_validate_judge_entrypoints -q
git diff --check
```

修改 OpenCode harness ledger / worker / retry 逻辑后：

```text
python -B -m unittest validation.tools.test_opencode_agent_harness -q
git diff --check
```

修改 competition runner / summary schema 后：

```text
python -B -m unittest validation.tools.test_run_competition validation.tools.test_validate_competition_run_summary -q
git diff --check
```

修改双语 roadmap/docs 后：

```text
python -B -m unittest validation.tools.test_doc_mirror_contract -q
git diff --check
```

提交前至少核对：

```text
git status --short
git diff --check
```

推送后核对：

```text
git rev-parse HEAD
git rev-parse origin/codex/flashdb-rust-skeleton
gh run list --branch codex/flashdb-rust-skeleton --limit 5 --json databaseId,headSha,status,conclusion,workflowName,url
```

## 不要做的事

1. 不要声称 H9 已关闭，除非有真实 `OpenCode + GLM-5.1 + c2rust-migrator + max` evidence。
2. 不要删除 `flashDB_rust`。
3. 不要直接删除 `openspec/`；先做退役迁移。
4. 不要把 local simulation、hostless rehearsal、Codex 子任务输出当 semantic gate。
5. 不要为扩 C 语法覆盖牺牲 harness 复现性和证据链。
6. 不要把未跟踪文档随手提交进功能 commit。
7. 不要并行改同一份 schema、validator 或 evidence 文件。

## 接手时的第一组命令

建议下一位 Agent 开始后先运行：

```text
cd /d F:\agent\crustpaper\0630
git status --short
git log --oneline -8
git rev-parse HEAD
git rev-parse origin/codex/flashdb-rust-skeleton
python -B -m unittest validation.tools.test_run_competition_smoke validation.tools.test_validate_judge_entrypoints -q
```

如果这些和本文不一致，以当前命令输出为准。

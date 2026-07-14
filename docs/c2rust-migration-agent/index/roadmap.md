英文镜像见 `roadmap.en.md`。

# 覆盖与路线

- [COVERAGE.md](../COVERAGE.md)
- [COVERAGE.en.md](../COVERAGE.en.md)
- [future-vision-and-mvp.md](../future-vision-and-mvp.md)
- [future-vision-and-mvp.en.md](../future-vision-and-mvp.en.md)

## A19b4c2 检索前沿

- [x] **A19b4c2a：把上下文检索未就绪建模为可恢复调度态，而不是 semantic ledger 终态。** portfolio 显式列出 `pending_retrieval_groups`，同时保留 hash-bound assignments；scheduler 对这些 worker 返回 `context_retrieval_pending` defer，因此它们不会获得租约，也不会触发模型调用。控制器用例验证 attempts/leases 均为 0；有限回归在 Windows 与 WSL 均为 527/527。该项只证明 pending 分类、绑定保留和零租约/零模型边界，不宣称 pending 已能恢复为 `ready`，也不构成 semantic gate 或增加 translator numerator。
- [x] **A19b4c2b：实现 host-owned、content-bound 的 single-SCC refresh/override。** host 会重开 portfolio、base/new catalog、selection receipt、page/group、refresh input 与 overlay 的完整 CAS 依赖，之后才以私有 permit 把 SCC 从 `pending_retrieval` 恢复为 `ready`；dispatch、request 与 prelaunch 会再次重开 overlay，任一漂移都在 attempt/provider 前 fail closed。
- [x] **A19b4c2c：在每波结束后重算下一检索前沿。** host 从绑定 portfolio 的 DAG、上一波 last-good 状态、显式失败证据与 expansion query 派生 wave input 和每 SCC selection directives；整波失效在一个 SQLite 事务中完成，逐 SCC refresh 可在中断后用相同 CAS 输入幂等续跑，且旧 schema refresh、跨 SCC fact 注入、旧/未来 query epoch 与调用方身份字段均被拒绝。该闭环可由 `prepare-next-context-frontier-wave` 调用，仍保持 `semantic_gate=false`、`translation_coverage_numerator=0`。
- [x] **A19b4c2d：根计划只保存 hash-bound portfolio 摘要。** `project-migration-plan.json` 不再复制完整 assignments、ledger units 和 context；dispatch 在同一文件句柄上流式复验 path/size/SHA，要求 canonical UTF-8 JSON，并核对 run/status/DAG/portfolio-plan 身份后才进入不可变 ledger 复验。完整 CIndex、ContextPages 和 portfolio 仍需继续分片，因此父项保持未勾选。

## 评委 Demo / Milestone

当前公开 before/after 入口是 `../judge-demo.md`。
机器可读的评委入口目录是 `../../../config/competition-env/judge-entrypoints/flashdb-harness.json`，其中集中绑定 competition environment smoke、FlashDB before/after demo、普通显式多 worker evaluate profile、OpenCode 显式多 worker evaluate profile、预期 artifacts（含 `worker_plan`）、tracked manifests 和 claim boundary。

全量评委 public packet 入口：

```bash
python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
```

该命令成功后会在同目录生成 `judge-milestone-bundle.json`、`milestone-release-notes.md` 和 `public-release-packet.json`。bundle 是机器可读外部评估索引，Markdown notes 是从 bundle 渲染的人类可读 release notes，JSON public release packet hash 绑定 run report、readiness report、bundle、notes 和 competition config archive，并由 `validate_public_release_packet` 校验 schema、hash、claim boundary、本机路径泄漏、packet-to-bundle 内容一致性，以及 notes 是否等于 bundle 渲染结果；这些产物都不是 semantic gate，也不增加 `translation_coverage_numerator`。

runner 对每个 entrypoint 命令默认施加 36000 秒有限超时，可用 `--timeout-seconds` 覆盖；超时会在 run report 中写入 `entrypoint.timeout_policy`、`root_cause_key=process_timeout` 和 `exit_code=124`，然后 fail-closed。

focused smoke/triage 入口示例：

```bash
python3 -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --entrypoint-id competition_environment_smoke --out target/h7-judge-smoke/summary/judge-entrypoints-run-report.json
```

聚焦运行成功后，runner 会在 report 同目录写出 `selected-entrypoints-validation-config.json`，post-run local-artifact 深校验只检查本次选中的 entrypoint，并同步收窄 `test_contract.required_entrypoint_ids`。这用于 smoke/triage，不是全量 public packet；外部发布仍应使用不带 `--entrypoint-id` 的全量入口。

启用 `--require-local-artifacts` 时，`validate_judge_entrypoints` 还会通过 `validate_competition_run_summary.py` 深校验非 smoke `competition_summary`，覆盖 workflow metrics、before/after refs、repair history、unsafe 账本、final-gate 规则和 slice counts。

同一 public packet 现在把 C2Rust baseline manifest 状态纳入 route-governance 与 milestone scorecard：`raw_c2rust.c2rust_baseline_rollup` 按 evidence root 去重并展示 manifest/source/compile-pass 数，同时保持 raw C2Rust `semantic_gate=false`、`translation_coverage_numerator=0`；typed-IR generated-draft acceptance 独立计数。coverage matrix 当前派生 `translator_generated_semantic_pass_count=24`，包括 `real-fdb-calc-crc32`、`real-fdb-blob-make`、`real-fdb-is-str`、`real-fdb-kv-del`、`real-fdb-kv-set`、`real-fdb-kv-to-blob`、`real-fdb-new-kv-alloc-compare`、`real-fdb-tsl-to-blob`、`zlib-ng/adler32-step` 和一组 demo exact typed-IR drafts。

首选真实 FlashDB 运行路径：

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
```

审计展开版：

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
```

关键 artifacts：

- `target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/context-pack.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/agent-index.json`

边界：`milestone-review-checklist.json` / review gate 只作为 release readiness 与公开 claim boundary 的审计输入，不是 semantic acceptance gate，也不会增加 `translation_coverage_numerator`。

当前 harness-first 开发入口：

```bash
python3 -B -m validation.tools.opencode_agent_harness evaluate --run-id run-evaluate --target-id flashdb --source-repo-root <repo-relative-source-root> --source-file <source.c> --source-commit <commit> --out-root target/competition-out-evaluate --proof-class local-simulation --max-workers 4
```

该入口会产出 `harness/evaluate-report.json`、`harness/context-pack.json`、`harness/agent-index.json`、`harness/resume-manifest.json` 和 SQLite `context_packs` 索引，用于评委审计和下一轮 OpenCode 多 agent 续跑；其中 `context_management_contract` / `agent_coordination_contract` 会把 plan -> worker fan-out -> verify/merge -> repair loop -> report 的角色边界、resume protocol 和 `chat_output_is_evidence=false` 明确落成机器可读字段。`resume-manifest.json` 是 current-state 续跑索引，绑定 context/agent sha、SQLite ledger、worker summaries 和 repair hints，但不是 semantic gate，也不增加 `translation_coverage_numerator`。

Profile 形式的一键入口：

```bash
python3 -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json --run-id harness-flashdb-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701
```

该路径会复用完整 batch-profile pipeline，并额外产出 `harness/evaluate-report.json` wrapper 和 `harness/judge-evidence-index.json`；二者只索引已验证的 batch artifacts、summary validator 和 context/index，不是新的语义接受门禁。

OpenCode 显式多 worker 评委入口：

```bash
python3 -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json --run-id harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-opencode-explicit-workers-evaluate-profile-20260701
```

该路径额外绑定 OpenCode preflight、`opencode_agent_runtime`、worker handoff/session/log、`worker_plan`、`context-pack.json`、`agent-index.json` 和 `judge-evidence-index.json`；`validate_judge_entrypoints --require-local-artifacts` 会校验 runtime contract 与 sha256。边界：OpenCode chat/session 不是语义证据，也不是新的 semantic gate。

如果 OpenCode 在第一条 shell command 前报 `database is locked`，worker 会把有限启动重试记录为 `opencode_process_retries`。这个重试只服务 runtime 稳定性；worker 是否能进入 merge 仍由 contract verification 和 summary validation 决定。

保底 repo-local demo：

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
```

审计展开版：

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

保底 artifacts：

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`

边界：真实 FlashDB exhibit 为 `real-fdb-calc-crc32` 绑定 accepted-evidence before/after artifacts，并记录 unsafe 2 -> 0。`judge-demo-report.json.repair_summary` 只聚合已绑定 workflow metrics / before-after exhibit 中的 repair/retry/rollback 字段，不能替代 validator 或 oracle。C2Rust baseline 现在具有 generated + compile-only + direct replay observable-passed evidence，但仍为 `candidate_context_only` / `semantic_pass=false`；typed-IR generated Rust draft 只有 exact draft 的 `generated_draft_acceptance.status=passed` 才计入 translator-generated semantic pass，当前 numerator 为 22。

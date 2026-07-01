英文镜像见 `roadmap.en.md`。

# 覆盖与路线

- [COVERAGE.md](../COVERAGE.md)
- [COVERAGE.en.md](../COVERAGE.en.md)
- [future-vision-and-mvp.md](../future-vision-and-mvp.md)
- [future-vision-and-mvp.en.md](../future-vision-and-mvp.en.md)

## 评委 Demo / Milestone

当前公开 before/after 入口是 `../judge-demo.md`。
机器可读的评委入口目录是 `../../../config/competition-env/judge-entrypoints/flashdb-harness.json`，其中集中绑定 competition environment smoke、FlashDB before/after demo、普通显式多 worker evaluate profile、OpenCode 显式多 worker evaluate profile、预期 artifacts（含 `worker_plan`）、tracked manifests 和 claim boundary。

全量评委 public packet 入口：

```bash
python -B -m validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --out target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json
```

该命令成功后会在同目录生成 `judge-milestone-bundle.json`、`milestone-release-notes.md` 和 `public-release-packet.json`。bundle 是机器可读外部评估索引，Markdown notes 是从 bundle 渲染的人类可读 release notes，JSON public release packet hash 绑定 run report、readiness report、bundle、notes 和 competition config archive，并由 `validate_public_release_packet` 校验 schema、hash、claim boundary、本机路径泄漏、packet-to-bundle 内容一致性，以及 notes 是否等于 bundle 渲染结果；这些产物都不是 semantic gate，也不增加 `translation_coverage_numerator`。

启用 `--require-local-artifacts` 时，`validate_judge_entrypoints` 还会通过 `validate_competition_run_summary.py` 深校验非 smoke `competition_summary`，覆盖 workflow metrics、before/after refs、repair history、unsafe 账本、final-gate 规则和 slice counts。

首选真实 FlashDB 运行路径：

```bash
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
```

审计展开版：

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
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
python -B -m validation.tools.opencode_agent_harness evaluate --run-id run-evaluate --target-id flashdb --source-repo-root <repo-relative-source-root> --source-file <source.c> --source-commit <commit> --out-root target/competition-out-evaluate --proof-class local-simulation --max-workers 4
```

该入口会产出 `harness/evaluate-report.json`、`harness/context-pack.json`、`harness/agent-index.json`、`harness/resume-manifest.json` 和 SQLite `context_packs` 索引，用于评委审计和下一轮 OpenCode 多 agent 续跑；其中 `context_management_contract` / `agent_coordination_contract` 会把 plan -> worker fan-out -> verify/merge -> repair loop -> report 的角色边界、resume protocol 和 `chat_output_is_evidence=false` 明确落成机器可读字段。`resume-manifest.json` 是 current-state 续跑索引，绑定 context/agent sha、SQLite ledger、worker summaries 和 repair hints，但不是 semantic gate，也不增加 `translation_coverage_numerator`。

Profile 形式的一键入口：

```bash
python -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json --run-id harness-flashdb-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701
```

该路径会复用完整 batch-profile pipeline，并额外产出 `harness/evaluate-report.json` wrapper 和 `harness/judge-evidence-index.json`；二者只索引已验证的 batch artifacts、summary validator 和 context/index，不是新的语义接受门禁。

OpenCode 显式多 worker 评委入口：

```bash
python -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json --run-id harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-opencode-explicit-workers-evaluate-profile-20260701
```

该路径额外绑定 OpenCode preflight、`opencode_agent_runtime`、worker handoff/session/log、`worker_plan`、`context-pack.json`、`agent-index.json` 和 `judge-evidence-index.json`；`validate_judge_entrypoints --require-local-artifacts` 会校验 runtime contract 与 sha256。边界：OpenCode chat/session 不是语义证据，也不是新的 semantic gate。

如果 OpenCode 在第一条 shell command 前报 `database is locked`，worker 会把有限启动重试记录为 `opencode_process_retries`。这个重试只服务 runtime 稳定性；worker 是否能进入 merge 仍由 contract verification 和 summary validation 决定。

保底 repo-local demo：

```bash
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
```

审计展开版：

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

保底 artifacts：

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`

边界：真实 FlashDB exhibit 为 `real-fdb-calc-crc32` 绑定 accepted-evidence before/after artifacts，展示 unsafe 2 -> 0。`judge-demo-report.json.repair_summary` 只汇总已绑定 workflow metrics / before-after exhibit 中的 repair/retry/rollback 字段，不替代 validator 或 oracle。C2Rust baseline output remains skipped，`generated_draft_semantic_pass=false`，该 exhibit 不增加 `translation_coverage_numerator`。

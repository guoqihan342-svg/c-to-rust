英文镜像见 `judge-demo.en.md`。

# 评委 Demo 入口

首选评委路径：真实 FlashDB `real-fdb-calc-crc32`。
保底路径：repo-local `demo/store-add-one`。

这份文档面向“核心翻译功能 + harness 架构”两条评分轴，展示同一条证据链：原始 unsafe Rust、最终 safe Rust、accepted patch、oracle evidence、unsafe before/after、五阶段 harness contract 和 milestone report。

## 真实 FlashDB 一键路径

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit --review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json
```

审计展开版：

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python3 -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --review-checklist target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
```

关键 FlashDB artifacts：

- `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-review-checklist.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/judge-evidence-index.json`
- H5 上下文包：`target/competition-out-flashdb-before-after-exhibit/harness/context-pack.json`
- agent 索引：`target/competition-out-flashdb-before-after-exhibit/harness/agent-index.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/workflow-metrics.json`
- baseline unsafe Rust：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-baseline-unsafe.rs`
- final safe Rust：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-final-safe.rs`
- accepted safety patch：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-accepted-safety.patch`
- safety step log：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-safety-step-log.jsonl`
- before/after manifest：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-translation-before-after.json`
- H4 run manifest：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-h4-baseline-repair-run.json`，入库记录 `harness-h4-flashdb-context-index-20260701` 的复现命令、target run artifact hash、attempt 1/2 repair trace 和 `translation_coverage_numerator=0` 边界。

绑定的真实 slice 是 `sources/FlashDB/src/fdb_utils.c#fdb_calc_crc32`，commit 为 `f9d0421315c564fb890a1b14eee77b290e0d7bbe`。核心 per-unit unsafe 数字是 `real-fdb-calc-crc32`：baseline unsafe count `2`，final unsafe count `0`，`reduced_by=2`。

边界：before/after exhibit 当前 baseline 仍是从真实 C slice signature 派生并人工 review 的 unsafe Rust baseline；C2Rust baseline 现在已有 generated + compile-only + direct replay observable-passed evidence，但仍是 `candidate_context_only` / `semantic_pass=false`，不能声称 before/after baseline 来自 verified C2Rust output。该 exhibit 本身不新增 semantic gate；另一路 exact `real-fdb-calc-crc32` typed-IR generated draft 已通过 `generated_draft_acceptance.status=passed`，所以 route/milestone metrics 的 translator-generated numerator 当前为 1。

Harness 自愈展示：`flashdb-fdb-utils-before-after` profile 现在声明 `attempt_evidence_policy.mode=baseline_repair_gate`。第 1 轮 worker 产出 baseline unsafe gate 失败 summary，root cause 为 `unsafe_baseline_requires_repair`；第 2 轮必须携带 repair hint，随后复验 accepted safe evidence。`harness/context-pack.json` 和 `harness/agent-index.json` 都索引该 policy 与两轮 attempt timeline。

## 保底 Demo 一键路径

```bash
python3 -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
```

审计展开版：

```bash
python3 -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python3 -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
python3 -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

保底 demo artifacts：

- `target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/judge-evidence-index.json`
- H5 上下文包：`target/competition-out-demo-before-after-exhibit/harness/context-pack.json`
- agent 索引：`target/competition-out-demo-before-after-exhibit/harness/agent-index.json`
- `target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-demo-before-after-exhibit/summary/workflow-metrics.json`
- baseline unsafe Rust：`validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-baseline-unsafe.rs`
- final safe Rust：`validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-final-safe.rs`
- accepted safety patch：`validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-accepted-safety.patch`
- unsafe scan：`validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-before-after-unsafe-scan.json`
- safety step log：`validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-safety-step-log.jsonl`
- before/after manifest：`validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json`

保底 demo 展示 `demo/store-add-one` 的 unsafe 3 -> 0。

## Claim 边界

- `judge-demo-report.json` 是一条命令入口的总报告，绑定 `competition-run-summary.json`、`workflow-metrics.json`、`before-after-exhibit.json`、`milestone-release-report.json` 和复制后的 `milestone-review-checklist.json` 的路径与 sha256。
- `harness/judge-evidence-index.json` 是同形状评委证据索引，绑定 `judge-demo-report.json`、summary、workflow metrics、before/after exhibit、milestone、context pack、agent index、run/merge/worker plan 的路径与 sha256；它不是 semantic gate，也不自引用。
- review checklist / review gate 只作为 release readiness 输入和审计证据，不是 semantic acceptance gate，也不会增加 `translation_coverage_numerator`。
- `judge-demo-report.json.repair_summary` 汇总 repair/retry/rollback 展示字段，包括 repair round cap、auto recovery、root cause counts、repair history 和 rollback ids；它只来自已绑定的 workflow metrics / before-after exhibit，不替代 validator 或 oracle。
- `before-after-exhibit.json` 是评委展示入口，证明 artifact binding、unsafe delta 和 harness contract；它不替代 `competition-run-summary.json`、`workflow-metrics.json` 或 evidence validator。
- before/after 展品固定声明 `generated_draft_semantic_pass=false`；展品中的安全化候选不能冒充 translator-generated semantic pass。
- `harness/context-pack.json` 和 `harness/agent-index.json` 是 `run-batch-profile` 生成的 H5 harness 审计索引与多 agent 续跑入口，展示 planner/worker/merge/report 拓扑和 worker assignment；它们不替代 summary、validator 或 oracle，也不扩大 semantic pass claim。
- `translation_coverage_numerator` 不会因为这些 exhibit 增加；coverage numerator 只能统计通过对应 gate 的 translator-generated named slice。
- 所有公开路径必须保持 repo-relative；不要把本机绝对路径或 WSL host path 写进公开 claim。

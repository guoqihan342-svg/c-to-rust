英文镜像见 `judge-demo.en.md`。

# 评委 Demo 入口

首选评委路径：真实 FlashDB `real-fdb-calc-crc32`。
保底路径：repo-local `demo/store-add-one`。

这份文档面向“核心翻译功能 + harness 架构”两条评分轴，展示同一条证据链：原始 unsafe Rust、最终 safe Rust、accepted patch、oracle evidence、unsafe before/after、五阶段 harness contract 和 milestone report。

## 真实 FlashDB 一键路径

```bash
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
```

审计展开版：

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
```

关键 FlashDB artifacts：

- `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/workflow-metrics.json`
- baseline unsafe Rust：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-baseline-unsafe.rs`
- final safe Rust：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-final-safe.rs`
- accepted safety patch：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-accepted-safety.patch`
- safety step log：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-safety-step-log.jsonl`
- before/after manifest：`validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-translation-before-after.json`

绑定的真实 slice 是 `sources/FlashDB/src/fdb_utils.c#fdb_calc_crc32`，commit 为 `f9d0421315c564fb890a1b14eee77b290e0d7bbe`。核心 per-unit unsafe 数字是 `real-fdb-calc-crc32`：baseline unsafe count `2`，final unsafe count `0`，`reduced_by=2`。

边界：baseline 是从真实 C slice signature 派生并人工 review 的 unsafe Rust baseline。C2Rust baseline output remains skipped，因此不能声称该 baseline 来自真实 C2Rust 输出。`generated_draft_semantic_pass=false`，该 exhibit 也不增加 `translation_coverage_numerator`。

## 保底 Demo 一键路径

```bash
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
```

审计展开版：

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

保底 demo artifacts：

- `target/competition-out-demo-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json`
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

- `judge-demo-report.json` 是一条命令入口的总报告，绑定 `competition-run-summary.json`、`workflow-metrics.json`、`before-after-exhibit.json` 和 `milestone-release-report.json` 的路径与 sha256。
- `judge-demo-report.json.repair_summary` 汇总 repair/retry/rollback 展示字段，包括 repair round cap、auto recovery、root cause counts、repair history 和 rollback ids；它只来自已绑定的 workflow metrics / before-after exhibit，不替代 validator 或 oracle。
- `before-after-exhibit.json` 是评委展示入口，证明 artifact binding、unsafe delta 和 harness contract；它不替代 `competition-run-summary.json`、`workflow-metrics.json` 或 evidence validator。
- `translation_coverage_numerator` 不会因为这些 exhibit 增加；coverage numerator 只能统计通过对应 gate 的 translator-generated named slice。
- 所有公开路径必须保持 repo-relative；不要把本机绝对路径或 WSL host path 写进公开 claim。

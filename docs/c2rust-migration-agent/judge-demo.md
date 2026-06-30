英文镜像见 `judge-demo.en.md`。

# 评委 Demo 入口

本文是当前分支的最短公开演示路径，面向“核心翻译功能 + harness 架构”两条评分轴。它使用 repo-local demo slice 展示同一条证据链：原始 unsafe Rust、最终 safe Rust、accepted patch、oracle evidence、unsafe before/after、五阶段 harness contract 和 milestone report。

## 一键运行

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/demo-store-add-one-before-after.json --run-id competition-demo-before-after-exhibit --out-root target/competition-out-demo-before-after-exhibit
python -B validation/tools/validate_competition_run_summary.py --summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json
```

运行 profile 后，关键展示 artifact 是：

- `target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-demo-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-demo-before-after-exhibit/harness/batch-profile-report.json`
- `target/competition-out-demo-before-after-exhibit/summary/competition-run-summary.json`
- `target/competition-out-demo-before-after-exhibit/summary/workflow-metrics.json`

## Before/After 证据

当前 demo 绑定的翻译质量证据位于：

- baseline unsafe Rust: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-baseline-unsafe.rs`
- final safe Rust: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-final-safe.rs`
- accepted safety patch: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-accepted-safety.patch`
- unsafe scan: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-before-after-unsafe-scan.json`
- safety step log: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-safety-step-log.jsonl`
- before/after manifest: `validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json`

该 demo 的核心数字是 per-unit `unsafe_reduction`: baseline unsafe count `3`，final unsafe count `0`，`reduced_by=3`。语义边界由 C oracle / Rust replay / final verification 绑定，harness 只负责把证据串成可复现的 planner -> worker -> verifier -> repairer -> reporter contract。

## Claim Boundary

- `generated_draft_semantic_pass=false`：这里展示的是 accepted-evidence-authoritative 的 before/after 安全化证据，不把 generated draft 自身包装成 semantic pass。
- `translation_coverage_numerator` 不会因为这个 demo 增加；coverage numerator 只能统计 translator-generated candidate 且通过对应 gate 的 named slice。
- `before-after-exhibit.json` 是评委展示入口，证明 artifact 绑定、unsafe delta 和 harness contract；它不替代 `competition-run-summary.json`、`workflow-metrics.json` 或 evidence validator。
- 所有路径必须保持 repo-relative；不要把本机绝对路径或 WSL host path 写进公开 claim。

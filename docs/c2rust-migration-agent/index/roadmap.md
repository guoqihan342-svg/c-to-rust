英文镜像见 `roadmap.en.md`。

# 覆盖与路线

- [COVERAGE.md](../COVERAGE.md)
- [COVERAGE.en.md](../COVERAGE.en.md)
- [future-vision-and-mvp.md](../future-vision-and-mvp.md)
- [future-vision-and-mvp.en.md](../future-vision-and-mvp.en.md)

## 评委 Demo / Milestone

当前公开 before/after 入口是 `../judge-demo.md`。
机器可读的评委入口目录是 `../../../config/competition-env/judge-entrypoints/flashdb-harness.json`，其中集中绑定 FlashDB before/after demo、显式多 worker evaluate profile、预期 artifacts、tracked manifests 和 claim boundary。

首选真实 FlashDB 运行路径：

```bash
python -B -m validation.tools.judge_demo --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
```

审计展开版：

```bash
python -B -m validation.tools.opencode_agent_harness run-batch-profile --profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json --run-id competition-flashdb-before-after-exhibit --out-root target/competition-out-flashdb-before-after-exhibit
python -B validation/tools/milestone_release_report.py --competition-summary target/competition-out-flashdb-before-after-exhibit/summary/competition-run-summary.json --batch-profile-report target/competition-out-flashdb-before-after-exhibit/harness/batch-profile-report.json --output target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json
```

关键 artifacts：

- `target/competition-out-flashdb-before-after-exhibit/summary/before-after-exhibit.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/judge-demo-report.json`
- `target/competition-out-flashdb-before-after-exhibit/summary/milestone-release-report.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/context-pack.json`
- `target/competition-out-flashdb-before-after-exhibit/harness/agent-index.json`

当前 harness-first 开发入口：

```bash
python -B -m validation.tools.opencode_agent_harness evaluate --run-id run-evaluate --target-id flashdb --source-repo-root <repo-relative-source-root> --source-file <source.c> --source-commit <commit> --out-root target/competition-out-evaluate --proof-class local-simulation --max-workers 4
```

该入口会产出 `harness/evaluate-report.json`、`harness/context-pack.json`、`harness/agent-index.json` 和 SQLite `context_packs` 索引，用于评委审计和下一轮 OpenCode 多 agent 续跑。

Profile 形式的一键入口：

```bash
python -B -m validation.tools.opencode_agent_harness evaluate --profile config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json --run-id harness-flashdb-explicit-workers-evaluate-profile-20260701 --out-root target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701
```

该路径会复用完整 batch-profile pipeline，并额外产出 `harness/evaluate-report.json` wrapper 和 `harness/judge-evidence-index.json`；二者只索引已验证的 batch artifacts、summary validator 和 context/index，不是新的语义接受门禁。

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

## Why

当前全量回归已经覆盖编译、测试、FlashDB replay/diff、stress、OpenSpec 和 git diff，但它还没有把已有 L2/L3 evidence 当作强制门禁消费。这样会出现“验证基础设施在跑，但关键证据漂移、缺失或负向校验失效时仍可能绿灯”的风险。

本变更把全量回归从命令集合升级为 evidence-aware gates：每轮必须刷新或校验 L2 evidence summary、FlashDB L3 manifest、负向 diff、unsafe 报告、版本绑定和测试翻译覆盖矩阵，确保自动翻译闭环的验证证据可以被机器稳定复查。

## What Changes

- 在 full regression 中增加 L2 evidence gate：刷新 L2 reports，并校验每个 L2 slice 都有 Rust report、positive diff、negative diff、unsafe scan/ledger 和 test translation 覆盖证据。
- 在 full regression 中增加 FlashDB L3 manifest gate：校验已接受 L3 evidence manifest 的必需引用、状态、fixture/source binding、negative diff mutation detection 和 unsafe/version/config evidence。
- 增加 FlashDB fixture negative diff gate：对 committed fixture 的 expected report 做受控突变，确认 diff-report 会失败并记录失败证据。
- 增强 FlashDB unsafe scan：支持写入 JSON report，并扫描 `unsafe fn`、unsafe block、`unsafe impl`、`extern "C"`、`repr(C)`、`transmute`、raw pointer 等 ledger 相关类别。
- 增加 version/config binding gate：校验 version manifest 与 repo 中声明的工具、schema、Cargo package 和 OpenSpec 版本一致，防止缓存和 evidence 在版本漂移后被误用。
- 增加 coverage/test-translation gate：校验 L2 和自动翻译 evidence 中的 test translation 覆盖主路径、错误路径和负向用例，不把“只有 Rust 编译通过”当成等价性证据。
- 不引入新的在线 AI 依赖；AI 仍只允许作为候选生成或修复建议，不作为正确性证据。

## Capabilities

### New Capabilities

- `full-regression-evidence-gates`: Covers executable evidence gates for full regression, including L2 summary validation, L3 manifest validation, negative diff controls, unsafe scan reports, version/config binding, and test translation coverage checks.

### Modified Capabilities

- `bounded-auto-translation-pipeline`: Final acceptance must be consumable by the full-regression evidence gates, not only by per-slice validators.
- `flashdb-l3-agent-migration-loop`: FlashDB L3 evidence must include machine-checkable manifest, negative diff, unsafe report, and version/config binding that full regression can validate each round.

## Impact

- Affected scripts: `scripts/run-full-regression.ps1`.
- Affected validation tools: `validation/tools/*.py`, `validation/l2_slices/src/bin/emit_reports.rs`.
- Affected FlashDB CLI/tests: `flashDB_rust/src/cli.rs`, `flashDB_rust/tests/*.rs`.
- Affected evidence/docs: `validation/evidence/**`, `validation/gates.md`, OpenSpec specs under this change.
- Dependencies: no required new Rust/Python third-party dependency; checks use existing stdlib, Cargo, OpenSpec, and committed evidence.

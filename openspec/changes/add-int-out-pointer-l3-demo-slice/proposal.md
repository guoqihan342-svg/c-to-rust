## Why

上一轮已经让翻译器能识别并生成 `out[0]` 这种受限输出指针写入，但证据仍停留在翻译器单元测试和 auto_migrate JSON 层。需要补一条最小 L3 demo slice，把 `out[0]` 从候选翻译能力推进到 C oracle、Rust replay、差分、负向差分、unsafe 审计和回归门禁的完整闭环。

这能避免项目继续只在“验证基础设施”层面增长，也为后续真实项目中的指针输出函数提供可复制的自动翻译闭环样板。

## What Changes

- 新增 `store_add_one(int value, int* out)` demo slice，覆盖 `out[0] = value + 1; return 0;` 的受限输出指针写入。
- 为该 slice 自动生成或登记 context pack、pointer graph、type map、CFG、Rust draft/replay、C oracle、schema diff、negative diff、unsafe scan 和 summary evidence。
- 将该 slice 纳入现有轻量验证路径，确保 1 轮 smoke 能验证该证据链而不显著增加运行成本。
- 保持 Rust 公共边界 safe，不暴露 raw pointer，并继续阻断未证明的指针索引或指针算术。

## Capabilities

### New Capabilities
- `int-out-pointer-l3-demo-slice`: 定义 `store_add_one` 受限输出指针 slice 的 L3 自动翻译证据链和门禁行为。

### Modified Capabilities
- `bounded-auto-translation-pipeline`: 补充 `out[0]` 指针输出 slice 在 auto_migrate 证据中的必备 lvalue/pointer decision 字段。

## Impact

- Affected code: `validation/slice-specs/`, `validation/tools/auto_migrate.py`, `validation/tools/test_auto_migrate.py`, `validation/l2_slices/`, `validation/evidence/`, `scripts/run-full-regression.ps1`
- Affected evidence: 新增 `store-add-one` 相关 oracle/replay/diff/unsafe/manifest JSON。
- No breaking changes: 只新增一个受限 demo slice 和门禁检查，不改变现有 FlashDB、libuv、zlib evidence 语义。

## Why

上一轮已经让 translator 识别并记录 bounded direct call expression，但目前还停留在 translator/unit evidence 层。为了让“跨文件深度关联上下文管理”继续往前走，需要一个 L3 demo slice 证明 call expression 能进入 C oracle、Rust replay、diff、negative diff、unsafe scan、auto evidence manifest 和短回归 gate。

## What Changes

- 新增 `demo-call-expression` L3 slice，使用递归 direct call expression 覆盖 declaration initializer、assignment RHS、return expression 三个主路径。
- 新增 C oracle fixture、safe Rust replay、Rust 测试、schema diff、negative diff、performance smoke、unsafe scan/ledger 和 L3 summary evidence。
- 新增 slice spec，并通过 `auto_migrate --accept-existing-evidence` 绑定 translator 的 `call_expressions` / `direct_call_edges` evidence。
- 接入 L2/L3 summary validator 和 full-regression 的 auto evidence semantic gate。
- 不声明任意 callee 语义、跨文件函数体内联、函数指针调用或宏调用已解决。

## Capabilities

### New Capabilities
- `call-expression-l3-demo-slice`: 用 L3 demo slice 验证 bounded direct call expression 的端到端证据链。

### Modified Capabilities
- `bounded-auto-translation-pipeline`: call expression evidence 必须能进入 normalized plan/context pack 和 accepted L3 evidence binding。

## Impact

- `validation/l2_slices/`: 新增 Rust replay module、测试、C oracle generator 和 fixture。
- `validation/l2_slices/src/bin/emit_reports.rs`: 新增 demo evidence emission、negative diff、performance smoke、unsafe ledger 和 summary entry。
- `validation/slice-specs/`: 新增 `demo-call-expression.json`。
- `validation/tools/`: 新增 L3 evidence 测试，扩展 L2/L3 evidence summary mapping。
- `scripts/run-full-regression.ps1`: 新增 `demo-call-expression-auto-evidence-semantic` step。

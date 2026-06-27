# Candidate Route P0 设计（当前两路线修订）

本文是中文主文档。英文版本见 `2026-06-27-candidate-route-p0-design.en.md`。

## 当前结论

本文件取代早期三路线 P0 草案。当前 typed IR candidate generation 模型只有两条路线：

- `GenericTypedIr`：通用 typed IR emitter 成功生成 Rust candidate。
- `Unsupported`：typed IR emitter fail closed，没有生成 Rust candidate，错误中保留 route metadata 和 fail-closed reason。

`DeprecatedLegacyCrc32`、typed IR crc32 matcher 和 typed IR canned emitter 已从当前 typed IR route 模型中删除。旧字符串 translator 的 crc32 byte-cursor recognizer 和 canned Rust 模板也已删除；raw string crc32 byte-cursor 输入现在 fail closed，除非它先通过 clang-lowered typed IR + globals 进入 `GenericTypedIr`。该模板不能作为 typed IR fallback 或 legacy parser fallback 被重新引入。

## 目标

P0 的目标是让 `c2r-translator` 的 typed IR 候选生成显式返回 route metadata，并让自动翻译证据把该候选生成 provenance 绑定到 `route_decision.candidate_generation.typed_ir` 和 `validation_profile.candidate_generation`。

成功状态：

- typed IR 成功只记录 `GenericTypedIr`。
- typed IR 不支持只记录 `Unsupported`，并且不生成 Rust draft。
- candidate generation 永远不设置 semantic acceptance；`semantic_pass` 必须保持 `false`。
- `generated_draft_semantic_pass` 必须保持 `false`，除非后续独立 validation gates 显式提升该 exact draft。

## 非目标

- 不实现完整 L0/L1/L2/L3/L4 evidence router。
- 不让 candidate route 决定 `validation_profile` 或 `semantic_pass`。
- 不接 LLM candidate generation。
- 不把旧 crc32 模板恢复为 typed IR fallback。
- 不把 generated Rust draft 当作语义通过证据。
- 不让 `GenericTypedIr` 覆盖 pointer graph 已记录的 alias 风险 floor；P0 只补最小 route floor，不实现完整多路线调度器。

## 核心类型

当前 `translation_route.rs` contract：

```rust
pub enum CandidateRoute {
    GenericTypedIr,
    Unsupported,
}

pub enum CandidateGenerator {
    GenericTypedIrEmitter,
    None,
}

pub struct CandidateRouteDecision {
    pub route_id: String,
    pub route: CandidateRoute,
    pub candidate_generator: CandidateGenerator,
    pub reasons: Vec<CandidateRouteReason>,
    pub fallback: Option<CandidateRoute>,
    pub token_cost: u32,
    pub deprecated: bool,
    pub replacement: Option<CandidateRoute>,
    pub delete_when: Vec<String>,
    pub suggested_required_gates: Vec<String>,
}

pub struct EmittedRust {
    pub rust: String,
    pub route: CandidateRouteDecision,
}
```

`deprecated=false`、`replacement=None`、`delete_when=[]` 是当前两路线模型的正常状态。schema 中不允许 typed IR candidate route 使用 `DeprecatedLegacyCrc32`。

## Route 规则

### GenericTypedIr

当 generic typed IR emitter 成功：

- `route = GenericTypedIr`
- `candidate_generator = GenericTypedIrEmitter`
- `rust_draft_generated = true`
- `semantic_pass = false`
- `suggested_required_gates` 可以建议 `rustc_smoke` 和 `typed_ir_contract_tests`

### Unsupported

当 generic typed IR emitter fail closed：

- `route = Unsupported`
- `candidate_generator = None`
- `rust_draft_generated = false`
- `semantic_pass = false`
- `unsupported_reason` 保留 fail-closed 细节
- `suggested_required_gates` 可以包含 `manual_review`

## candidate_generation 证据

`route_decision.candidate_generation` 和 `validation_profile.candidate_generation` 使用同一份 typed IR binding。profile 中的对象必须与 route decision 中的对象相同。

```json
{
  "typed_ir": {
    "status": "generated",
    "source_artifact": {
      "path": "validation/evidence/.../l3-<slice>-clang-lowering-report.json",
      "sha256": "<sha256>",
      "status": "lowered"
    },
    "candidate_route": {
      "route_id": "generic-typed-ir",
      "route": "GenericTypedIr",
      "candidate_generator": "GenericTypedIrEmitter",
      "token_cost": 0,
      "deprecated": false
    },
    "readonly_globals": [],
    "readonly_globals_identity": {
      "count": 0,
      "names": [],
      "sha256": "<sha256>"
    },
    "rust_draft_generated": true,
    "semantic_pass": false
  }
}
```

不支持时，`typed_ir.status = "unsupported"`，`candidate_route.route = "Unsupported"`，`rust_draft_generated = false`，并记录 `unsupported_reason`。

schema 的兼容规则：`candidate_generation` 对未带 candidate_generation 的历史 evidence artifacts 仍是可选字段；一旦出现，就必须满足当前两路线 typed IR contract。这样不会破坏旧 evidence tests，但会拒绝新证据重新引入 `DeprecatedLegacyCrc32` 或 `semantic_pass=true`。

## 与 evidence route decision 的关系

typed IR `CandidateRouteDecision` 只回答：

```text
这个 typed IR Rust candidate 是由哪个生成器产生，或为什么没有产生？
```

`validation/tools/auto_migrate.py` 的 evidence route decision 仍回答：

```text
这个 slice 的候选生成路径、验证 profile、证据绑定状态是什么？
```

二者不能混用：

- candidate route 不设置 acceptance。
- candidate route 不覆盖 L4/refuse 语义，也不覆盖 `alias_blocked`、`requires_noalias_contract` 或未知 pointer ownership floor。
- generated Rust draft 只是 candidate evidence。
- semantic acceptance 仍由 C oracle、Rust replay、schema diff、negative diff、unsafe ledger、final verification 等 gates 决定。

当前 route decision 的最小风险 floor：

- `GenericTypedIr` generated 仍会写入 `candidate_generation.typed_ir` 和 rationale。
- 若 pointer graph 已记录 `alias_contract.decision="blocked"`，路线保持 L3，不降到 L1。
- 若 pointer graph 已记录 `requires_noalias_contract` 或 `unknown_alias` risk，路线保持 L2，不降到 L1。
- 若 pointer ownership role 仍为 `unknown`，路线保持 L2。

## 验证策略

最小验证：

1. `translation_route.rs` enum 只包含 `GenericTypedIr` 和 `Unsupported`。
2. `clang-lowering-report.typed_ir_candidate` 记录 `semantic_pass=false`。
3. `route_decision.candidate_generation.typed_ir` 与 clang-lowering-report 中的 typed IR candidate 一致。
4. `validation_profile.candidate_generation` 与 route decision 完全一致。
5. schema 接受没有 `candidate_generation` 的历史 evidence artifacts，但拒绝包含 `DeprecatedLegacyCrc32` 或 `semantic_pass=true` 的新 typed IR candidate evidence。
6. `GenericTypedIr` candidate 不能覆盖 alias route floor：`requires_noalias_contract` / `unknown_alias` 路由到 L2，`alias_blocked` 路由到 L3。
7. clang lowering 产生的 `GenericTypedIr` direct-call candidate 必须写出与 bounded direct call 匹配的 `call_expressions` 证据，同时保持 `semantic_pass=false`。
8. 如果 slice spec 声明 external direct callee，默认 validator 和 `--require-semantic-pass` 都必须逐 call-site 校验 plan `translation_summary.call_expressions`、context-pack `direct_call_edges`、`callee_sources`、`signature_bindings` 和 `call_edge_to_callee_binding` 的 source/signature/stub/semantics 边界一致；这只是 evidence integrity/provenance hardening，不代表 external callee 语义已通过。
9. clang lowering 产生的局部固定长度整数数组元素写入可以进入 `GenericTypedIr`，但 readonly global array 写入、const pointer slice 写入、VLA 和 array-to-pointer decay 必须继续 fail closed，且仍只代表 candidate generation，不代表 semantic acceptance。
10. `GenericTypedIr` 的标量整数 `*`、`/`、`%` candidate 必须保持 `semantic_pass=false`，且不能覆盖 alias floors、除零风险或指针算术边界；除法/取模只有在非零 divisor 由 literal、fixture 输入域或 slice contract 明确约束时，才可进入后续 semantic gate。
11. `GenericTypedIr` 的 signed 标量 unary minus `-value` candidate 必须保持 `semantic_pass=false`；operand/result 必须是同一个 signed integer scalar type，unsigned/wrapping 取负、浮点取负、指针算术、复合 `-=`、以及 `-2147483648` 这类 literal 边界继续 fail closed。
12. `GenericTypedIr` 的 logical not `!expr` candidate（条件位置 + 窄 value-position）必须保持 `semantic_pass=false`；`if (!x)` / `while (!x)` 可发射为整数零比较，`!(x > 0)` 可发射为反转 comparison，`return !x` / assignment RHS / declaration initializer 等 value-position 可 materialize 为 C `int` 0/1；call/inc/dec/deref 副作用、pointer/float/unsupported type、短路逻辑和完整 C unary `!` 继续 fail closed。
13. `GenericTypedIr` 的 comparison expression candidate（条件位置 + 窄 value-position C `int` 0/1 materialization）必须保持 `semantic_pass=false`；`if` / `while` 中的标量整数比较可发射为 Rust bool condition，`return x > 0` / assignment RHS / declaration initializer 等 value-position 可 materialize 为 C `int` 0/1；pointer comparison、float comparison、mixed-width/unsigned conversions、comparison cast operand、call/inc/dec/deref 等 side-effect operands、short-circuit `&&` / `||` 和 semantic acceptance 继续 fail closed。

建议验证命令：

```powershell
python validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id call-expression
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32
```

如需验证 Rust route contract，可继续运行现有 `crates/c2r-translator` 测试；route floor 还应运行 `validation.tools.test_auto_migrate` 中的 typed IR route signal 用例。

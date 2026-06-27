## Why

The bounded C-to-Rust pipeline already generates alias-gate evidence for several pointer slices, but the reusable templates did not fully describe the contract. That gap makes later struct-pointer and alias-sensitive work easy to overclaim: the validator may require alias fields while the schema and examples fail to teach new slices how to produce them.

中文：当前有界 C-to-Rust 管线已经能为部分 pointer slice 生成 alias gate evidence，但通用模板没有完整描述这个契约。这个缺口会让后续 struct pointer 和 alias-sensitive 翻译容易高估能力：验证器可能已经要求 alias 字段，但 schema 和 example 没有告诉新 slice 应如何产出这些字段。

## What Changes

- Add pointer graph template support for `alias_contract`, `alias_risks`, `safe_boundary_preconditions`, `effect_graph`, and per-node read/write effects.
- Add slice spec template support for `c_boundary.pointer_contract` and `memory_model`.
- Add auto-translation plan and L3 evidence manifest schema support for alias-gate summaries.
- Update examples and checklists so alias safety is described as bounded evidence, not as whole-program proof.

中文：

- 在 pointer graph 模板中补齐 `alias_contract`、`alias_risks`、`safe_boundary_preconditions`、`effect_graph` 和每个 pointer node 的读写 effect。
- 在 slice spec 模板中补齐 `c_boundary.pointer_contract` 和 `memory_model`。
- 在 auto-translation plan 与 L3 evidence manifest schema 中补齐 alias-gate summary。
- 更新示例和清单，明确 alias safety 是有边界的证据契约，不是全程序证明。

## Impact

- `validation/pointer-graph-template/`
- `validation/slice-spec-template/`
- `validation/auto-translation-template/`
- `validation/l3-template/`
- `validation/tools/test_template_schema_contracts.py`
- `openspec/specs/bounded-auto-translation-pipeline/spec.md`

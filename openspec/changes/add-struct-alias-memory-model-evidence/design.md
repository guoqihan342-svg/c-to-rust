## Context

FlashDB is only a validation use case. The reusable contract must serve arbitrary C projects where pointer reads, pointer writes, struct fields, callbacks, or external mutable state affect the Rust boundary.

中文：FlashDB 只是验证用例。通用契约必须适用于任意 C 项目，只要它的 pointer read、pointer write、struct field、callback 或 external mutable state 会影响 Rust 边界。

## Design

The alias/memory-model evidence is split into four layers:

- Slice input: `c_boundary.pointer_contract` records pointer roles, length companions, read/write effects, alias proof status, read-read allowances, and required noalias pairs.
- Slice memory model: `memory_model` records the higher-level alias contract, ownership contract, length companions, and effect graph assumptions.
- Pointer graph: `alias_contract`, `alias_risks`, `alias_sets`, `safe_boundary_preconditions`, `effect_graph`, and per-node read/write effects capture the generated evidence after context/type/CFG extraction.
- Claim propagation: `translation_summary.alias_gate`, auto manifest claim boundary, L3 manifest claim boundary, final verification, and cache metadata carry the decision so acceptance cannot silently drop alias risk.

中文：

- Slice 输入层：`c_boundary.pointer_contract` 记录 pointer role、length companion、read/write effect、alias proof 状态、允许的 read-read alias，以及必须 noalias 的 pointer 组。
- Slice memory model 层：`memory_model` 记录更高层的 alias contract、ownership contract、length companion 和 effect graph 假设。
- Pointer graph 层：`alias_contract`、`alias_risks`、`alias_sets`、`safe_boundary_preconditions`、`effect_graph` 和每个 node 的 read/write effect 记录 context/type/CFG 抽取后的证据。
- Claim 传播层：`translation_summary.alias_gate`、auto manifest claim boundary、L3 manifest claim boundary、final verification 和 cache metadata 承接这个决策，避免 acceptance 静默丢失 alias 风险。

## Compatibility

The initial schema change is additive. It declares the missing fields and updates examples, but does not require every historical evidence file to be migrated immediately. Runtime validators continue to fail closed for alias-sensitive generated evidence.

中文：本次 schema 变化先保持 additive，只声明缺失字段并更新 example，不要求立刻迁移所有历史 evidence。运行时验证器继续对 alias-sensitive 生成证据 fail-closed。

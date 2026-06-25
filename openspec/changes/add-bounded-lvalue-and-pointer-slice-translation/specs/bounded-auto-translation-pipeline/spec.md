## ADDED Requirements

### Requirement: LValue Decision Evidence Is Preserved
The automatic translation pipeline SHALL preserve lvalue and pointer-boundary decisions from the translator artifacts into normalized L3 evidence.

自动翻译管线必须把 translator 产出的 lvalue 与 pointer-boundary 决策保留到规范化 L3 evidence 中。

#### Scenario: Normalized CFG records lvalue kinds
- **WHEN** the translator emits CFG evidence for a slice containing supported or blocked lvalue writes
- **THEN** normalized `l3-<slice>-cfg.json` records statement kinds and lvalue kinds for the affected statements
- **AND** the information is available without parsing the generated Rust draft

#### Scenario: Normalized pointer graph records boundary decisions
- **WHEN** the translator emits pointer graph evidence for a pointer-bearing slice
- **THEN** normalized `l3-<slice>-pointer-graph.json` records whether each pointer write is a safe wrapper candidate, bounded pointer index, unsupported alias, or unsupported complex lvalue
- **AND** the auto-translation manifest references that pointer graph status before semantic acceptance

#### Scenario: Translation plan records lvalue rule ids
- **WHEN** a supported lvalue write is translated
- **THEN** normalized `l3-<slice>-auto-translation-plan.json` records the translation rule id for that lvalue class
- **AND** unsupported lvalue counts remain visible when the draft is blocked

### Requirement: Pointer LValue Candidates Remain Evidence-Bound
The automatic translation pipeline SHALL treat pointer/lvalue generated Rust as candidate evidence until C oracle, Rust replay, diff, negative diff, unsafe, and version/config gates pass.

自动翻译出的 pointer/lvalue Rust 只能是候选 evidence，不能因为编译通过就声明语义等价。

#### Scenario: Rust check pass is not semantic pass
- **WHEN** a pointer/lvalue Rust draft compiles successfully
- **THEN** the manifest status remains candidate unless accepted oracle and replay evidence are present
- **AND** `claim_boundary.semantic_pass` remains false without full L3 evidence

#### Scenario: Unsupported lvalue blocks candidate generation
- **WHEN** the translator records an unsupported lvalue decision
- **THEN** auto_migrate writes blocked repair or blocked translation evidence
- **AND** the run does not mark the Rust draft gate as passed

## MODIFIED Requirements

### Requirement: Evidence Package Captures Translation Artifacts
The auto-translation pipeline SHALL emit a deterministic evidence package for each attempted slice migration, including the context pack, pointer graph, type map, CFG, generated Rust draft or blocked repair report, and validation summary.

自动翻译管线必须为每个 slice 迁移尝试产出 deterministic evidence package，包括 context pack、pointer graph、type map、CFG、Rust draft 或 blocked repair report，以及验证摘要。

#### Scenario: Successful bounded function slice emits required artifacts
- **WHEN** a single-function C slice is accepted by the bounded translator
- **THEN** the pipeline writes context pack, pointer graph, type map, CFG, generated Rust draft, and summary files
- **AND** the summary records the source function name, target Rust entry point, translation status, and validation commands

#### Scenario: Blocked slice preserves repair evidence
- **WHEN** a slice is rejected because it is outside the bounded subset
- **THEN** the pipeline writes blocked repair evidence with the unsupported construct, source location where available, and proposed next action
- **AND** it does not claim semantic equivalence for that slice

#### Scenario: Bounded out pointer slice records lvalue and pointer decisions
- **WHEN** a C slice writes through a proven `out[0]` output pointer
- **THEN** the pipeline records `pointer_index_zero` or equivalent bounded lvalue classification in the CFG evidence
- **AND** the pointer graph records the base pointer, index boundary, write effect, and safe public boundary decision
- **AND** the generated Rust draft or replay evidence records that raw pointer exposure was avoided

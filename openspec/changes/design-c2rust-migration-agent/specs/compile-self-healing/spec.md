## ADDED Requirements

### Requirement: Structured rustc error handling
The migration system SHALL run `cargo check --message-format=json` for compile validation and parse rustc JSON messages into structured error stacks with primary spans, related spans, error codes, rendered messages, and suggested fixes.

编译自愈必须从 rustc JSON error stack 开始，而不是把长日志直接丢给 AI。
#### Scenario: cargo check fails
- **WHEN** `cargo check --message-format=json` reports errors
- **THEN** the Agent groups errors by root cause and affected span
- **THEN** the Agent stores the structured error event in the context store

### Requirement: Minimal PatchPlan
The migration system SHALL produce a minimal PatchPlan before applying compile repairs. A PatchPlan MUST include files, spans, reason, expected error delta, risk, rollback id, and whether AI was used.

每次自动补丁必须有最小 PatchPlan，禁止全局搜索式乱补。
#### Scenario: Fixing a type mismatch
- **WHEN** rustc reports `E0308`
- **THEN** the Agent checks type mappings, newtypes, slices, and `Result` or `Option` wrappers
- **THEN** the PatchPlan edits only the affected span or approved adapter

### Requirement: Repair strategy limits
The migration system SHALL use deterministic rules before AI. AI MAY be used only for low-certainty ownership, lifetime, signature, or semantic-difference diagnosis. Repair attempts MUST have a bounded retry limit and MUST roll back when the limit is exceeded.

自愈先用规则，低确定性问题才调用 AI；超过轮次必须回滚并记录债务。
#### Scenario: Borrow repair cannot be proven
- **WHEN** `E0499`, `E0502`, or lifetime errors remain after rule-based repair
- **THEN** the Agent may call AI with a bounded context pack and explicit forbidden changes
- **THEN** the Agent rejects repairs that increase unregistered unsafe or break semantic tests

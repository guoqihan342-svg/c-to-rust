## ADDED Requirements

### Requirement: Structured rustc error handling
The migration system SHALL run `cargo check --message-format=json` for compile validation and parse rustc JSON messages into structured error stacks with primary spans, related spans, error codes, rendered messages, and suggested fixes.

缂栬瘧鑷剤蹇呴』浠?rustc JSON error stack 寮€濮嬶紝鑰屼笉鏄妸闀挎棩蹇楃洿鎺ヤ涪缁?AI銆?
#### Scenario: cargo check fails
- **WHEN** `cargo check --message-format=json` reports errors
- **THEN** the Agent groups errors by root cause and affected span
- **THEN** the Agent stores the structured error event in the context store

### Requirement: Minimal PatchPlan
The migration system SHALL produce a minimal PatchPlan before applying compile repairs. A PatchPlan MUST include files, spans, reason, expected error delta, risk, rollback id, and whether AI was used.

姣忔鑷姩琛ヤ竵蹇呴』鏈夋渶灏?PatchPlan锛岀姝㈠叏灞€鎼滅储寮忎贡琛ャ€?
#### Scenario: Fixing a type mismatch
- **WHEN** rustc reports `E0308`
- **THEN** the Agent checks type mappings, newtypes, slices, and `Result` or `Option` wrappers
- **THEN** the PatchPlan edits only the affected span or approved adapter

### Requirement: Repair strategy limits
The migration system SHALL use deterministic rules before AI. AI MAY be used only for low-certainty ownership, lifetime, signature, or semantic-difference diagnosis. Repair attempts MUST have a bounded retry limit and MUST roll back when the limit is exceeded.

鑷剤鍏堢敤瑙勫垯锛屼綆纭畾鎬ч棶棰樻墠璋冪敤 AI锛涜秴杩囪疆娆″繀椤诲洖婊氬苟璁板綍鍊哄姟銆?
#### Scenario: Borrow repair cannot be proven
- **WHEN** `E0499`, `E0502`, or lifetime errors remain after rule-based repair
- **THEN** the Agent may call AI with a bounded context pack and explicit forbidden changes
- **THEN** the Agent rejects repairs that increase unregistered unsafe or break semantic tests

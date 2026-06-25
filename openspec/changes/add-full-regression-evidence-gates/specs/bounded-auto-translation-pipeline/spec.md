## ADDED Requirements

### Requirement: Automatic Translation Evidence Is Consumable By Full Regression
The system SHALL make accepted automatic translation evidence consumable by the full-regression evidence gates before the translation can be treated as accepted project evidence.

#### Scenario: Auto translation manifests are validated in full regression
- **WHEN** an automatic translation run declares a slice accepted
- **THEN** full regression validates the slice evidence manifest, context pack, type map, CFG, pointer graph, test translation, C oracle, Rust report, schema diff, negative diff, rust check, unsafe scan, unsafe ledger, version/config binding, and final verification for that slice

#### Scenario: Per-slice pass is not enough
- **WHEN** a generated Rust draft compiles and its targeted replay test passes
- **THEN** the automatic translation is still not accepted unless the full-regression evidence gates can consume and validate its final evidence

#### Scenario: Missing optional AI does not block evidence gates
- **WHEN** no online AI provider is configured for the automatic translation run
- **THEN** full regression continues to validate deterministic evidence and accepts `AI_SKIPPED` only when no AI output is required for the accepted claim

### Requirement: Automatic Translation Test Coverage Is Explicit
The system SHALL bind generated or translated tests to the same slice fixture and evidence root used by automatic translation.

#### Scenario: Generated tests reference source fixture cases
- **WHEN** automatic translation emits Rust replay test evidence
- **THEN** the evidence maps each generated Rust assertion to source C oracle or fixture cases and records coverage of main, boundary, error, and negative-diff cases where applicable

#### Scenario: Coverage gaps are reported as blocked evidence
- **WHEN** the translator cannot generate a Rust replay test for a fixture case
- **THEN** the test translation evidence records the gap and the slice cannot be accepted by full regression until the gap is resolved or explicitly scoped out in the slice contract

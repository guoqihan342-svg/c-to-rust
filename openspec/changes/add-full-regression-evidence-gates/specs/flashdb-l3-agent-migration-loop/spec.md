## ADDED Requirements

### Requirement: FlashDB L3 Evidence Is Consumable By Full Regression
The system SHALL bind accepted FlashDB L3 slice evidence to full-regression gates so that repeated regression runs can independently re-check the claim.

#### Scenario: FlashDB L3 manifest is checked per round
- **WHEN** a full regression round runs after a FlashDB L3 slice has accepted evidence
- **THEN** the round validates the slice evidence manifest and referenced C oracle, Rust report, schema diff, negative diff, unsafe scan, unsafe ledger, version/config binding, performance smoke, test translation, and final verification reports

#### Scenario: FlashDB L3 acceptance fails on evidence drift
- **WHEN** an accepted FlashDB L3 evidence file is missing, has mismatched fixture/source binding, loses negative mutation detection, or violates unsafe/version policy
- **THEN** full regression fails before reporting the branch as green

### Requirement: FlashDB L3 Negative Controls Are Re-Executable
The system SHALL keep FlashDB L3 negative controls executable from committed or generated evidence, not only documented as historical artifacts.

#### Scenario: Negative diff can be rerun
- **WHEN** the full regression gate evaluates a FlashDB L3 slice
- **THEN** it can rerun or revalidate the negative diff control that mutates behavior fields and confirms schema-aware diff rejection

#### Scenario: Behavior mutation is not an accepted difference
- **WHEN** a FlashDB L3 negative mutation changes value, status, count, entry id, timestamp, operation success, or error semantics
- **THEN** the diff rejects the mutation and records the mismatch path

### Requirement: FlashDB L3 Unsafe Evidence Uses Expanded Categories
The system SHALL use expanded unsafe categories for FlashDB L3 evidence and ledger decisions.

#### Scenario: FFI and representation boundaries are visible
- **WHEN** FlashDB Rust source contains `extern "C"` or `repr(C)`
- **THEN** the unsafe evidence records these as boundary findings even if no unsafe block exists

#### Scenario: Raw pointer and transmute patterns are visible
- **WHEN** FlashDB Rust source contains raw pointer types, raw pointer dereference, pointer casts, or `transmute`
- **THEN** the unsafe evidence records their categories and requires ledger review before acceptance

## ADDED Requirements

### Requirement: Evidence-Aware Full Regression
The system SHALL run executable evidence gates during full regression and SHALL fail the round when required accepted evidence is missing, stale, malformed, or semantically negative-control-incomplete.

#### Scenario: Full regression executes evidence gates
- **WHEN** `scripts/run-full-regression.ps1` runs a round
- **THEN** the round includes L2 evidence validation, FlashDB L3 manifest validation, fixture negative diff validation, unsafe report validation, version/config binding validation, coverage/test-translation validation, OpenSpec validation, and git diff whitespace validation
- **AND** each evidence gate writes a per-round log or JSON report path into the full regression event stream

#### Scenario: Evidence gate failure stops the round
- **WHEN** an evidence gate reports missing required evidence, stale binding, failed negative control, invalid schema, or unsafe policy violation
- **THEN** the round status is `failed`
- **AND** the failed step log contains the evidence path and reason needed for compile/self-healing or manual repair

### Requirement: L2 Evidence Summary Gate
The system SHALL refresh and validate accepted L2 slice evidence before accepting full regression success.

#### Scenario: L2 evidence is refreshed before validation
- **WHEN** full regression reaches the L2 evidence phase
- **THEN** it runs the L2 report generator before validating L2 summaries
- **AND** the validator reads the generated Rust reports, positive diffs, negative diffs, unsafe scan, unsafe ledger, test translation evidence, and summary evidence from the same repository state

#### Scenario: Every accepted L2 slice has complete evidence
- **WHEN** an L2 slice is listed as accepted or passed in the L2 summary
- **THEN** that slice has a Rust report with `status=passed`, a positive diff with no behavioral mismatches, a negative diff with mutation detected, test translation coverage for main paths and negative cases, and unsafe scan plus unsafe ledger evidence

#### Scenario: Missing negative evidence blocks L2 success
- **WHEN** an accepted L2 slice lacks negative diff evidence or the negative diff does not detect a deliberate mutation
- **THEN** the L2 evidence gate fails

### Requirement: FlashDB L3 Manifest Gate
The system SHALL validate accepted FlashDB L3 evidence manifests against the L3 manifest contract during full regression.

#### Scenario: L3 manifest required evidence is present
- **WHEN** a FlashDB L3 evidence manifest declares `status=passed`
- **THEN** the validator confirms required evidence references exist for slice contract, context pack, cache metadata, config profile, pointer dependency graph, test translation, C oracle, Rust report, schema diff, negative diff, rust check, unsafe scan, unsafe ledger, performance smoke, final verification, summary, and version/config binding

#### Scenario: L3 manifest preserves fixture and source binding
- **WHEN** the L3 manifest references C oracle, Rust report, schema diff, and negative diff evidence
- **THEN** the validator confirms they refer to the same target id, slice id, fixture path or fixture hash where applicable, source commit, and repository commit or explicitly recorded local commit boundary

#### Scenario: L3 negative mutation is mandatory
- **WHEN** an L3 manifest has `status=passed`
- **THEN** its negative diff evidence records that a deliberate mutation was detected
- **AND** a missing or non-detecting negative diff fails the full regression gate

### Requirement: FlashDB Fixture Negative Control Gate
The system SHALL execute a negative control for committed FlashDB fixture diff validation.

#### Scenario: Fixture expected report mutation is rejected
- **WHEN** full regression compares `fixtures/ci-smoke.expected.json` against a deliberately mutated replay report or expected report
- **THEN** `diff-report` rejects the mutation
- **AND** the gate records a negative-control report showing the mismatch path

#### Scenario: Unexpected success is a failure
- **WHEN** the deliberate FlashDB fixture mutation is accepted by `diff-report`
- **THEN** full regression fails the negative control gate

### Requirement: Unsafe Scan Report Gate
The system SHALL produce and validate machine-readable unsafe scan evidence for FlashDB Rust code.

#### Scenario: Unsafe scan writes JSON report
- **WHEN** full regression runs `flashdb-unsafe-scan`
- **THEN** the command writes a JSON report containing schema version, scanned files, ignored paths, finding count, unsafe ratio, categories, and findings

#### Scenario: Unsafe categories are classified
- **WHEN** Rust source contains unsafe blocks, unsafe functions, unsafe impls, `extern "C"`, `repr(C)`, `transmute`, or raw pointer patterns
- **THEN** the unsafe scan report records the finding category, file, line, and source excerpt

#### Scenario: Unledgered unsafe fails the gate
- **WHEN** first-party non-test unsafe usage is non-zero
- **THEN** the gate fails unless every finding has ledger evidence and the unsafe ratio remains below 10%

### Requirement: Version And Config Binding Gate
The system SHALL validate version and config evidence before accepting full regression success.

#### Scenario: Version manifest is consumed
- **WHEN** full regression generates a FlashDB version manifest
- **THEN** a validator confirms the manifest includes Cargo package version, agent contract version, context schema version, patch plan schema version, fixture schema version, evidence schema version, rustc version, cargo version, OpenSpec version, and command arguments

#### Scenario: Version drift blocks cache reuse
- **WHEN** a version/config input used by evidence or cache binding is missing or differs from the repository-declared value
- **THEN** the version/config binding gate fails and reports the drift key

### Requirement: Coverage And Test Translation Gate
The system SHALL require accepted translation evidence to include machine-checkable test translation and coverage evidence.

#### Scenario: Test translation links C cases to Rust assertions
- **WHEN** an accepted L2 or L3 translation slice is validated
- **THEN** its test translation evidence maps source C oracle or fixture cases to Rust tests or replay assertions and records evidence links

#### Scenario: Main and negative paths are covered
- **WHEN** coverage evidence is validated for an accepted slice
- **THEN** it records covered main paths, error or boundary paths when present, and negative cases that prove the diff gate catches semantic mutation

#### Scenario: Coverage claims are bounded
- **WHEN** no production-data fixture, llvm-cov report, or symbolic verification artifact exists
- **THEN** the gate does not claim production-data equivalence, line coverage percentage, or exhaustive semantic equivalence

### Requirement: Evidence Searchability Gate
The system SHALL keep evidence traceable after every full regression round.

#### Scenario: Evidence search indexes generated reports
- **WHEN** full regression reaches evidence search
- **THEN** the search report includes the current round evidence directory and finds passed evidence records from earlier gate outputs

#### Scenario: Searchability does not replace validation
- **WHEN** evidence search finds matching text
- **THEN** full regression still relies on schema, summary, negative diff, unsafe, coverage, and version gates for acceptance

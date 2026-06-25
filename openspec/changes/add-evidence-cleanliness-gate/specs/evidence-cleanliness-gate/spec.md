## ADDED Requirements

### Requirement: Evidence Cleanliness Gate Is Explicit
The system SHALL provide an explicit full-regression gate that verifies committed evidence remains unchanged after evidence generators run.

#### Scenario: Cleanliness gate is opt-in
- **WHEN** `scripts/run-full-regression.ps1` runs without the evidence cleanliness option
- **THEN** the regression does not fail solely because the repository has intentional uncommitted `validation/evidence` edits

#### Scenario: Cleanliness gate checks committed evidence
- **WHEN** `scripts/run-full-regression.ps1` runs with the evidence cleanliness option enabled
- **THEN** the regression checks `validation/evidence/**` for tracked content differences after evidence-producing steps have run
- **AND** the round fails if tracked committed evidence differs from the working tree

#### Scenario: Cleanliness failure is diagnosable
- **WHEN** the evidence cleanliness gate fails
- **THEN** the failed step log includes the changed evidence paths
- **AND** the full-regression summary records the failed step name

### Requirement: Evidence Cleanliness Does Not Replace Evidence Validation
The system SHALL treat evidence cleanliness as a reproducibility check, not as a semantic correctness check.

#### Scenario: Existing evidence gates still run
- **WHEN** evidence cleanliness is enabled
- **THEN** L2 evidence validation, FlashDB L3 evidence validation, negative diff, unsafe, version binding, test translation coverage, OpenSpec validation, and git whitespace validation still run as their own gates

#### Scenario: Dynamic per-round reports are not cleanliness inputs
- **WHEN** a full-regression round writes reports under `target/full-regression/<run-id>/`
- **THEN** those per-round reports are not considered committed evidence drift by the cleanliness gate

## ADDED Requirements

### Requirement: Untracked Evidence Is A Cleanliness Failure
The system SHALL fail the explicit committed evidence cleanliness gate when `validation/evidence/**` contains untracked files.

#### Scenario: Untracked evidence is detected
- **WHEN** `scripts/run-full-regression.ps1` runs with the evidence cleanliness option enabled
- **AND** a file under `validation/evidence/**` is untracked by Git
- **THEN** the evidence cleanliness gate fails
- **AND** the failed step log includes the untracked evidence path

#### Scenario: Staged evidence drift is detected
- **WHEN** `scripts/run-full-regression.ps1` runs with the evidence cleanliness option enabled
- **AND** a tracked file under `validation/evidence/**` differs from `HEAD`, including staged differences
- **THEN** the evidence cleanliness gate fails
- **AND** the failed step log identifies the changed evidence path

#### Scenario: Default local regression remains permissive
- **WHEN** `scripts/run-full-regression.ps1` runs without the evidence cleanliness option
- **AND** a developer has intentional untracked files under `validation/evidence/**`
- **THEN** the regression does not fail solely because of the untracked evidence files

### Requirement: Evidence Cleanliness Scope Remains Bounded
The system SHALL limit untracked-file cleanliness checks to committed evidence inputs and SHALL NOT treat dynamic full-regression reports as evidence drift.

#### Scenario: Dynamic reports are excluded
- **WHEN** a full-regression round writes files under `target/full-regression/<run-id>/`
- **THEN** the untracked evidence cleanliness check ignores those files

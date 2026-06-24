## ADDED Requirements

### Requirement: Wave2 L1 attempts are recorded
The system SHALL attempt native C build/test smoke for at least 12 wave2 catalog targets.

#### Scenario: Minimum wave2 attempts are present
- **WHEN** wave2 L1 evidence is aggregated
- **THEN** the summary records attempted count at least 12
- **AND** every attempted target has per-project evidence

### Requirement: Per-project L1 evidence is complete
The system SHALL record pinned commit, external clone path, commands, exit codes, elapsed time, tool versions, and log paths for each attempted target.

#### Scenario: Project L1 evidence exists
- **WHEN** a target is attempted
- **THEN** `validation/evidence/<target>/l1-native-build.json` records status, commit, command steps, logs, and reporting boundary

### Requirement: L1 failures are preserved
The system SHALL preserve failed native build/test smoke attempts instead of dropping them from the summary.

#### Scenario: Failed attempt is auditable
- **WHEN** a build or smoke command fails or times out
- **THEN** the project evidence records status `failed`, the failed command, non-zero or timeout status, failure summary, and log paths

### Requirement: Wave2 L1 summary is bounded
The system SHALL summarize wave2 L1 results without claiming Rust migration or semantic equivalence.

#### Scenario: Summary avoids overclaim
- **WHEN** wave2 L1 summary is generated
- **THEN** it states that L1 proves only native C baseline build/test smoke
- **AND** it states that L2 Rust compilation and L3 C/Rust equivalence require separate evidence

### Requirement: Worker outputs are aggregatable
The system SHALL keep worker result files in external workspaces and aggregate compact evidence into the repository.

#### Scenario: Worker result source is recorded
- **WHEN** worker results are aggregated
- **THEN** the summary records each worker result source path and whether it loaded successfully

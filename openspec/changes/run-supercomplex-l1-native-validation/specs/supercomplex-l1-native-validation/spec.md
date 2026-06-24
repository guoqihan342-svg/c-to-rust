## ADDED Requirements

### Requirement: L1 evidence records pinned native baselines
The system SHALL record L1 native C build/test smoke evidence only for attempts that clone a specific upstream project and record the exact commit SHA used for the attempt.

#### Scenario: Passed native baseline
- **WHEN** a selected complex C project is cloned, built, and smoke-tested successfully
- **THEN** the evidence records status `passed`, the pinned commit SHA, build command exit code `0`, smoke command exit code `0`, elapsed time, tool versions, and external log paths

#### Scenario: Failed native baseline
- **WHEN** a selected complex C project clone, build, or smoke test fails
- **THEN** the evidence records status `failed`, the pinned commit SHA if available, the failed command, non-zero exit code, failure summary, elapsed time, and external log paths

### Requirement: L1 summary preserves reporting boundaries
The system SHALL aggregate L1 results without implying L2 Rust compilation or L3 semantic equivalence.

#### Scenario: Summary contains only L1 claims
- **WHEN** L1 worker results are aggregated
- **THEN** the summary states that L1 proves native C baseline reproducibility only and does not claim Rust migration success or C/Rust semantic equivalence

#### Scenario: Passed target count is explicit
- **WHEN** the summary is generated
- **THEN** it includes total attempts, passed count, failed count, and a per-project status list

### Requirement: External build artifacts stay out of the repository
The system SHALL keep upstream clones, build directories, and long raw logs outside the repository while retaining compact evidence in repo-local JSON.

#### Scenario: Evidence references external logs
- **WHEN** a build or smoke command writes stdout/stderr logs
- **THEN** the repo-local evidence references the external log paths instead of vendoring raw logs into the repository

### Requirement: L1 target threshold is enforced
The system SHALL treat the broad L1 validation milestone as incomplete until at least 12 catalog projects have passed L1 native build/test smoke.

#### Scenario: Fewer than 12 projects pass L1
- **WHEN** fewer than 12 selected projects have status `passed`
- **THEN** the summary records the milestone status as `incomplete`

#### Scenario: At least 12 projects pass L1
- **WHEN** 12 or more selected projects have status `passed`
- **THEN** the summary records the milestone status as `passed`

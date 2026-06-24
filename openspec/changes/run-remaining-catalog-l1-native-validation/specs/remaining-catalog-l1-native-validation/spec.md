## ADDED Requirements

### Requirement: Remaining catalog targets are attempted
The system SHALL attempt L1 native C build/test smoke for FFmpeg, MicroPython, Zephyr, and FreeRTOS Kernel.

#### Scenario: All remaining targets have L1 evidence
- **WHEN** remaining-catalog L1 evidence is aggregated
- **THEN** the summary records four attempted targets
- **AND** each attempted target has per-project evidence

### Requirement: Global L1 summary has no unattempted catalog targets
The system SHALL update the global L1 summary so every catalog target has a passed or failed L1 attempt.

#### Scenario: Catalog L1 attempt gap is closed
- **WHEN** the global L1 summary is generated
- **THEN** `attempted_count` equals `catalog_target_count`
- **AND** `not_attempted_catalog_projects` is empty

### Requirement: Failed attempts remain auditable
The system SHALL preserve failed or timed-out L1 attempts instead of dropping them from summaries.

#### Scenario: Failed remaining target is recorded
- **WHEN** a remaining target build or smoke command fails or times out
- **THEN** the project evidence records status `failed`, failed command label, exit code or timeout, failure summary, and log paths

### Requirement: Remaining L1 summary is bounded
The system SHALL summarize remaining-target L1 results without claiming Rust migration or semantic equivalence.

#### Scenario: Remaining summary avoids overclaim
- **WHEN** remaining-catalog L1 summary is generated
- **THEN** it states that L1 proves only native C baseline build/test smoke
- **AND** it states that Rust compilation, unsafe budget, performance, and C/Rust equivalence require separate evidence

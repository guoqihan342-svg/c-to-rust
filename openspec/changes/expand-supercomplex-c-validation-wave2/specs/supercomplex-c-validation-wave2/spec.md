## ADDED Requirements

### Requirement: Wave2 target expansion
The catalog SHALL contain at least 40 complex C or C-major validation targets after wave2 expansion.

#### Scenario: Catalog includes wave2 targets
- **WHEN** the catalog verifier runs
- **THEN** it requires at least 40 targets
- **AND** every target keeps the required validation metadata

### Requirement: Wave2 domains are diversified
The wave2 catalog additions SHALL include targets from kernel or virtualization, system services, networking or security, media or document processing, scientific data, and service infrastructure domains.

#### Scenario: New domains are represented
- **WHEN** the wave2 target list is inspected
- **THEN** it includes projects from at least six distinct high-complexity domains
- **AND** each new target records domain and complexity signals

### Requirement: Wave2 remote probe is auditable
The system SHALL generate L0 evidence for the expanded wave2 catalog by probing upstream HEAD and default branch.

#### Scenario: Remote probe records HEAD
- **WHEN** `validate-c-project-catalog.ps1 -ProbeRemote` runs
- **THEN** the evidence records `probe.ok`, `probe.default_branch`, and `probe.head_sha` for every catalog target
- **AND** default-branch mismatch fails the probe

### Requirement: Wave2 reporting boundary is explicit
The system SHALL report wave2 catalog validation as L0 only unless L1/L2/L3 evidence exists for a target.

#### Scenario: L0 is not overclaimed
- **WHEN** wave2 catalog evidence is summarized
- **THEN** the summary states that L0 remote validation is not native build, Rust migration, unsafe budget, C/Rust semantic equivalence, or performance preservation evidence

### Requirement: Wave2 project cards define follow-up work
The system SHALL provide practical L1/L2 follow-up cards for wave2 targets.

#### Scenario: Follow-up card is actionable
- **WHEN** an agent selects a wave2 target for deeper validation
- **THEN** project cards provide native build smoke, native test smoke, bounded Rust slice candidate, oracle strategy, and risk notes

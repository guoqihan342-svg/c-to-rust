## ADDED Requirements

### Requirement: Remediation candidates are bounded
The system SHALL only remediate L1 failures that can be addressed through catalog command or configuration changes without installing host packages, changing global toolchains, or claiming Rust migration equivalence.

#### Scenario: Candidate selection excludes host dependency failures
- **WHEN** low-cost remediation candidates are selected
- **THEN** projects requiring missing system packages, missing global build tools, network retry policy, or larger wrapper design are recorded as deferred
- **AND** they are not marked as remediated by this change

### Requirement: Catalog recipe changes are minimal and auditable
The system SHALL update `validation/projects.json` with the smallest command changes needed for accepted remediation candidates.

#### Scenario: Recipe change preserves validation scope
- **WHEN** a project catalog recipe is changed
- **THEN** the new commands preserve the original L1 smoke intent where practical
- **AND** any deliberate feature reduction such as disabling assembly, DCO, or broad tests is visible in the command text

### Requirement: Remediated projects are rerun
The system SHALL rerun every accepted remediation candidate and store machine-readable evidence for the rerun.

#### Scenario: Rerun evidence is generated
- **WHEN** the remediation validation run completes
- **THEN** the evidence records each attempted project, command outcomes, work root, log directory, passed count, and failed count
- **AND** per-project L1 evidence is refreshed for attempted projects

### Requirement: Global L1 summary reflects latest accepted evidence
The system SHALL update the global L1 native summary using the latest accepted evidence from remediation runs and prior successful runs.

#### Scenario: Summary separates passed and failed projects
- **WHEN** remediation evidence is aggregated
- **THEN** `validation/evidence/l1-native-summary.json` lists passed, failed, other, and not-attempted catalog projects consistently across all 40 catalog targets

### Requirement: Remediation report avoids overclaiming
The system SHALL report L1 remediation results as native C build/test smoke evidence only.

#### Scenario: Report states validation boundary
- **WHEN** the remediation report is generated
- **THEN** it states that L1 native smoke does not prove Rust compilation, unsafe budget compliance, C/Rust semantic equivalence, or performance preservation

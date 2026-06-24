## ADDED Requirements

### Requirement: Failed L1 projects are classified
The system SHALL classify every project listed in `failed_projects` from `validation/evidence/l1-native-summary.json`.

#### Scenario: Every failed project has a classification
- **WHEN** the L1 failure classifier runs
- **THEN** the JSON report contains one record for every failed project
- **AND** no failed project is omitted

### Requirement: Classifications preserve audit evidence
The system SHALL include enough evidence for a reviewer to audit each classification.

#### Scenario: Classification includes source evidence
- **WHEN** a failed project is classified
- **THEN** the report includes project id, failed step, failed command, exit code, timeout flag, evidence path, log paths, and a short log excerpt when available

### Requirement: Classifications are actionable
The system SHALL assign each failed project an actionable category and suggested next action.

#### Scenario: Category and next action are present
- **WHEN** classification output is generated
- **THEN** every failed project has a `category`, `confidence`, and `recommended_next_action`

### Requirement: Classification does not claim remediation
The system SHALL not report failed projects as fixed or passed.

#### Scenario: Classification preserves L1 status
- **WHEN** the failure classification report is generated
- **THEN** it states that classification is diagnostic only
- **AND** it does not modify project L1 status from failed to passed

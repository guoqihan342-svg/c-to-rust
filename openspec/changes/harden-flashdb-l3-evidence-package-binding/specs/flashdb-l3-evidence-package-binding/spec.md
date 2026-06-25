## ADDED Requirements

### Requirement: Positive Diff Evidence Is Content-Validated
The system SHALL validate the content of the positive FlashDB L3 schema diff report before accepting an L3 evidence package.

#### Scenario: Positive diff must pass
- **WHEN** `validate_flashdb_l3_evidence.py` validates a consumable FlashDB L3 package
- **THEN** the referenced positive diff report must have `status=passed`
- **AND** the referenced positive diff report must not record a `first_mismatch`

#### Scenario: Positive diff failure rejects the package
- **WHEN** the referenced positive diff report has a failed status or records a first mismatch
- **THEN** the FlashDB L3 evidence package validation fails with the slice id and diff label in the error

### Requirement: Final Verification Evidence Is Content-Validated
The system SHALL validate final verification evidence before accepting a FlashDB L3 evidence package.

#### Scenario: Final verification must pass
- **WHEN** `validate_flashdb_l3_evidence.py` validates a consumable FlashDB L3 package
- **THEN** the referenced final verification report must have `status=passed`
- **AND** any recorded diff status must be `passed`
- **AND** any recorded C oracle toolchain status must be `C_ORACLE_GENERATED`
- **AND** any recorded check entries must not contain failed status or non-zero exit code

#### Scenario: Final verification failure rejects the package
- **WHEN** final verification records a failed status, failed diff status, missing C oracle generation, failed check, or non-zero check exit code
- **THEN** the FlashDB L3 evidence package validation fails with the slice id and final verification label in the error

### Requirement: Summary Evidence Hashes Bind To Files
The system SHALL validate summary-declared evidence hashes when those hashes are present.

#### Scenario: Declared evidence hash matches file
- **WHEN** a FlashDB L3 summary evidence reference declares `sha256`
- **THEN** `validate_flashdb_l3_evidence.py` computes the referenced file hash
- **AND** the validation fails if the declared hash differs from the actual file hash

#### Scenario: Missing optional hash does not block legacy package
- **WHEN** a FlashDB L3 summary evidence reference does not declare `sha256`
- **THEN** the validator does not fail solely because the optional hash is absent

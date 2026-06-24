## ADDED Requirements

### Requirement: Slice scope is explicit
The system SHALL declare the project, pinned commit, C source boundary, Rust module, and fixture input domain for every L2 slice.

#### Scenario: Slice plan is recorded
- **WHEN** a slice is selected for L2 validation
- **THEN** its evidence includes project id, upstream commit, C source function or file boundary, Rust module path, and fixture input description

### Requirement: Rust slice compiles and is tested
The system SHALL compile and test each Rust slice using the Rust toolchain before claiming L2 passed.

#### Scenario: L2 Rust check passes
- **WHEN** `cargo test` is run for the L2 slice crate
- **THEN** all slice tests pass and the L2 evidence records the command, status, and tested modules

### Requirement: C oracle fixtures drive L3 comparison
The system SHALL compare Rust output with C oracle fixture output before claiming L3 passed for a slice.

#### Scenario: C/Rust diff passes
- **WHEN** C oracle fixtures and Rust slice reports are available for the same input cases
- **THEN** the diff evidence records status `passed`, case count, and no first mismatch

#### Scenario: C/Rust diff fails
- **WHEN** any Rust output differs from the C oracle for a behavior field
- **THEN** the diff evidence records status `failed`, first mismatch, case id, C value, and Rust value

### Requirement: Unsafe budget is enforced
The system SHALL record unsafe usage for the L2 slice crate and keep first-party non-test unsafe usage at 0 for this change.

#### Scenario: Unsafe scan passes
- **WHEN** the L2 slice crate is scanned for first-party non-test `unsafe`
- **THEN** evidence records unsafe count `0` and status `passed`

### Requirement: Reporting boundary is preserved
The system SHALL report L2/L3 success only for the named slice and fixture input domain.

#### Scenario: Summary avoids full-project claims
- **WHEN** L2/L3 evidence is summarized
- **THEN** the summary states that success does not prove full-project migration or global semantic equivalence

## ADDED Requirements

### Requirement: Multi-project validation catalog
The system SHALL maintain a checked-in catalog of at least 12 complex C or C-major projects for future C-to-Rust migration validation.

系统必须维护至少 12 个复杂 C 或 C 为主项目的候选验证目录。

#### Scenario: Catalog has enough diverse targets
- **WHEN** the catalog is validated
- **THEN** it contains at least 12 unique target ids
- **AND** each target has repository URL, domain, complexity signals, build smoke, migration slice, oracle strategy, and risk notes

### Requirement: Layered validation gates
The system SHALL define L0, L1, L2, and L3 gates so a shallow probe cannot be reported as full migration success.

系统必须区分远程探测、C 构建、迁移切片、语义差分等不同验证层级。

#### Scenario: Gate levels are explicit
- **WHEN** an agent reads the validation documentation
- **THEN** L0, L1, L2, and L3 each have passing criteria and evidence requirements

### Requirement: No-clone catalog verifier
The system SHALL provide a local verifier that validates catalog shape without cloning large repositories.

系统必须提供无需克隆大仓库的目录校验脚本。

#### Scenario: Offline validation succeeds
- **WHEN** the verifier runs without remote probing
- **THEN** it validates schema, required fields, unique ids, and minimum target count
- **AND** it writes a JSON evidence report

### Requirement: Optional remote probe
The verifier SHALL optionally probe remote repository HEADs with `git ls-remote` and record observed default branch and SHA.

远程探测必须显式开启，并记录默认分支和 HEAD SHA。

#### Scenario: Remote probe records current upstream state
- **WHEN** the verifier runs with remote probing enabled
- **THEN** each target records probe status, default branch, and HEAD SHA or failure detail

### Requirement: Non-equivalence boundary
The system SHALL state that catalog validation and remote reachability do not prove C-to-Rust migration equivalence.

系统必须明确目录验证不等于迁移完成，也不等于语义等价。

#### Scenario: Evidence level is not overstated
- **WHEN** only L0 validation has passed
- **THEN** generated evidence marks the level as `L0`
- **AND** documentation says deeper L1-L3 gates remain required before migration success can be claimed

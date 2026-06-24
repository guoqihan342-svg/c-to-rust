## ADDED Requirements

### Requirement: Reusable L3 evidence template
The system SHALL provide a reusable L3 evidence template under `validation/l3-template/` for bounded C-to-Rust migration slices.

系统必须在 `validation/l3-template/` 下提供可复用的 L3 证据模板，用于有边界的 C-to-Rust 迁移切片。

#### Scenario: Template files are present
- **WHEN** an agent prepares a future L3 migration slice
- **THEN** it can read `validation/l3-template/README.md`
- **AND** it can read `validation/l3-template/checklist.md`
- **AND** it can read `validation/l3-template/evidence-manifest.json`
- **AND** it can read `validation/l3-template/evidence-manifest.schema.json`
- **AND** it can read `validation/l3-template/evidence-manifest.example.json`

### Requirement: Required L3 evidence artifacts
The template SHALL identify the required evidence artifacts for an L3 semantic-equivalence claim.

模板必须标识 L3 语义等价声明所需的必备证据文件。

#### Scenario: Required evidence is enumerated
- **WHEN** the template manifest is inspected
- **THEN** it lists required artifacts for slice contract, context pack, cache metadata, C oracle, Rust replay, schema-aware diff, negative diff, rust check, unsafe scan, unsafe ledger, performance smoke, final verification, summary, and version or config binding
- **AND** each required artifact records expected status semantics

### Requirement: Negative diff is mandatory
The template SHALL require negative diff evidence proving the diff gate rejects an intentional behavior mismatch.

模板必须要求 negative diff 证据，以证明 diff 门禁能拒绝故意制造的行为不匹配。

#### Scenario: Positive diff alone is insufficient
- **WHEN** a slice has matching C and Rust reports but no negative diff evidence
- **THEN** the template marks the L3 claim as incomplete
- **AND** the summary must not claim semantic equivalence for the slice

### Requirement: Version and configuration binding
The template SHALL bind L3 evidence to source commit, fixture hash, toolchain or version manifest, and relevant feature or macro configuration.

模板必须把 L3 证据绑定到 source commit、fixture hash、toolchain 或 version manifest，以及相关 feature/macro 配置。

#### Scenario: Cached evidence cannot float across versions
- **WHEN** source commit, fixture hash, toolchain version, Cargo lock state, feature matrix, or macro configuration changes
- **THEN** the template requires regenerating or explicitly invalidating affected C oracle, Rust replay, diff, cache metadata, and summary evidence

### Requirement: Limited semantic-equivalence claim
The template SHALL require every L3 summary to state the exact claim scope and known gaps.

模板必须要求每个 L3 summary 写明精确声明范围和已知缺口。

#### Scenario: Summary cannot overclaim
- **WHEN** a slice reaches L3 passed status
- **THEN** its summary states the named slice, pinned source commit, fixture input domain, behavior fields checked, accepted metadata differences, and known non-goals
- **AND** it does not claim full-project migration, byte-for-byte image equivalence, power-loss recovery, GC or sector-layout parity, or unrelated slices unless those are separately proven

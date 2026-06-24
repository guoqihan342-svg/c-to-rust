## ADDED Requirements

### Requirement: L3 config profile artifact
The L3 validation template SHALL provide a reusable config-profile schema and example for L3 C-to-Rust migration slices.

中文：L3 验证模板必须为 L3 C-to-Rust 迁移切片提供可复用的 config-profile schema 和 example。

#### Scenario: Template exposes profile files
- **WHEN** an agent prepares a future L3 migration slice
- **THEN** it can read `validation/l3-template/config-profile.schema.json`
- **AND** it can read `validation/l3-template/config-profile.example.json`

### Requirement: Profile identity binds C and Rust evidence
The L3 validation template SHALL require a config-profile evidence reference that binds C oracle, Rust replay, diff, unsafe, performance, and summary evidence to the same normalized profile identity.

中文：L3 验证模板必须要求 config-profile 证据引用，把 C oracle、Rust replay、diff、unsafe、performance 和 summary 证据绑定到同一个规范化 profile identity。

#### Scenario: Required profile fields are present
- **WHEN** a future L3 evidence manifest references a config profile
- **THEN** the referenced config profile records `profile_id`, `source_commit`, `repo_commit`, `fixture.hash`, `config_header.path`, `config_header.sha256`, `c_defines`, `feature_matrix`, `compile_profile`, `rust_profile`, `toolchain`, and `cache_invalidation_keys`

### Requirement: Profile changes invalidate equivalence evidence
The L3 validation template SHALL treat config-profile changes as invalidating cached L3 equivalence evidence unless regenerated or explicitly justified by replacement evidence.

中文：当 config-profile 发生变化时，L3 验证模板必须把缓存的 L3 等价证据视为失效，除非重新生成或用替代证据明确说明。

#### Scenario: Macro or feature input changes
- **WHEN** the source commit, fixture hash, config header hash, C defines, feature matrix, compile command, include paths, Rust cargo features, Rust feature environment, backend, toolchain version, or Cargo lock hash changes
- **THEN** affected C oracle, Rust replay, diff, unsafe ledger, performance smoke, cache metadata, and summary evidence must be regenerated or explicitly invalidated

### Requirement: Config profile is not a macro solver
The L3 validation template SHALL state that config-profile evidence is a traceability and cache-invalidation gate, not proof that all possible macro activation conditions were explored.

中文：L3 验证模板必须说明 config-profile 证据是追溯与缓存失效门禁，而不是所有宏激活条件都已被探索的证明。

#### Scenario: Agent reports L3 pass
- **WHEN** an agent reports an L3 pass using config-profile evidence
- **THEN** it must not claim full macro expansion coverage, symbolic activation-condition coverage, async semantics, multithreaded semantics, or runtime cache semantics unless those are separately proven

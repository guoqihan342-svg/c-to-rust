## ADDED Requirements

### Requirement: L3 Version Manifest
The system SHALL generate a machine-readable version manifest for every FlashDB L3 migration slice before implementation edits or cache reuse.

系统必须在每个 FlashDB L3 迁移切片开始实现或复用缓存前，生成机器可读的 version manifest。

#### Scenario: Version manifest contains required version dimensions
- **WHEN** an L3 slice starts
- **THEN** the manifest records agent contract version, context schema version, PatchPlan schema version, output crate name and version, FlashDB source clone URL and commit, OpenSpec version, rustc version, cargo version, git version, fixture schema version, evidence schema version, Cargo.lock hash, host OS, and cache key inputs

#### Scenario: Missing optional tool versions are explicit
- **WHEN** a tool version cannot be detected
- **THEN** the manifest records `NOT_FOUND` for that tool and the affected gate decides whether the slice can continue

### Requirement: L3 Version Compatibility Gate
The system SHALL treat version drift as a cache invalidation and evidence review trigger before compile self-healing, C/Rust diff claims, or archive.

系统必须把版本漂移作为缓存失效和证据复核触发条件，且该检查必须发生在编译自愈、C/Rust diff 声明或归档之前。

#### Scenario: Version drift invalidates reusable artifacts
- **WHEN** FlashDB source commit, Rust crate version, Cargo.lock hash, fixture schema version, evidence schema version, agent contract version, context schema version, PatchPlan schema version, rustc version, cargo version, OpenSpec version, feature matrix, or command arguments change
- **THEN** cached ContextPack, PatchPlan suggestions, AI candidate patches, C oracle reports, and schema-aware diff conclusions are not reused without regeneration or explicit evidence review

#### Scenario: Version manifest is part of final evidence
- **WHEN** an L3 slice reaches final verification
- **THEN** the final verification evidence references the version manifest path and hash

### Requirement: Version Manifest CLI
The system SHALL expose a small Rust CLI command that emits the current migration version manifest without introducing new runtime dependencies or unsafe code.

系统必须暴露一个小型 Rust CLI 命令用于输出当前迁移 version manifest，且不得引入新的运行时依赖或 unsafe 代码。

#### Scenario: Version manifest command writes a report
- **WHEN** `flashdb-rust version-manifest --report <path>` is executed
- **THEN** it writes JSON containing `command:"version-manifest"`, `schema_version:1`, crate version, source commit, tool versions, schema versions, and cache key inputs to the requested report path

#### Scenario: Version manifest command prints JSON
- **WHEN** `flashdb-rust version-manifest` is executed without `--report`
- **THEN** it prints the same JSON to stdout

#### Scenario: Version command does not affect storage semantics
- **WHEN** the version manifest command runs
- **THEN** it does not create KVDB/TSDB flash images, does not run replay/diff, and does not change public database behavior

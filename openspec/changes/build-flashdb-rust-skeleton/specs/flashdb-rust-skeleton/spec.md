## ADDED Requirements

### Requirement: Compilable Rust project
The system SHALL create a `flashDB_rust` Rust project that builds as both a library crate and a small CLI executable.

系统必须创建可编译的 `flashDB_rust` Rust 工程，并同时提供 library crate 与 CLI smoke executable。

#### Scenario: Cargo build succeeds
- **WHEN** `cargo check` is run inside `flashDB_rust`
- **THEN** the Rust library and binary targets compile successfully

### Requirement: Module boundaries
The `flashDB_rust` project SHALL include clear modules for config, types, flash storage, format helpers, KVDB, TSDB, FFI boundary, and CLI behavior.

`flashDB_rust` 必须有清晰模块边界，避免后续迁移时跨文件调用关系失控。

#### Scenario: Module files exist
- **WHEN** the project skeleton is inspected
- **THEN** it contains module files for `config`, `types`, `flash`, `format`, `kvdb`, `tsdb`, `ffi`, and CLI entrypoints

### Requirement: Safe public API
The Rust-native public API SHALL NOT expose raw pointers and SHALL model fallible operations with Rust `Result`, optional values with `Option`, byte data with slices or owned vectors, and traversal with safe iterators or collected values.

Rust-native public API 不得暴露裸指针；C output parameter 风格必须转成 `Result`、`Option`、slice、owned value 或安全遍历接口。

#### Scenario: KVDB get returns optional data
- **WHEN** a caller reads a missing key through the Rust KVDB API
- **THEN** the API returns `Ok(None)` rather than a null pointer

### Requirement: Host flash backends
The project SHALL provide a deterministic memory flash backend and a file-backed flash backend with read, write, erase, flush, reopen, and operation counter behavior.

项目必须提供内存后端和文件后端；文件后端用于持久化与 reopen smoke 测试。

#### Scenario: File backend reopens data
- **WHEN** data is written through the file-backed backend and the database is reopened
- **THEN** previously committed values remain readable

### Requirement: KVDB seed behavior
The project SHALL implement initial host-verifiable KVDB behavior for string/blob set, get, delete, iteration, clear or GC-like compaction, and reopen.

项目必须先实现可主机验证的 KVDB 主干路径，作为后续完整 FlashDB layout 迁移的承载点。

#### Scenario: KVDB main path
- **WHEN** a test sets, reads, deletes, iterates, compacts, and reopens KVDB data
- **THEN** returned values, deleted state, iteration output, and reopened state are deterministic and correct for the Rust seed implementation

### Requirement: Basic TSDB seed behavior
The project SHALL implement basic TSDB append, query by time range, count by status, status update, and reopen behavior.

项目必须实现基础 TSDB 追加、查询、计数、状态更新和 reopen 行为。

#### Scenario: TSDB query count
- **WHEN** TSDB entries are appended with timestamps and queried by range and status
- **THEN** the returned entries and counts match the inserted sequence after reopen

### Requirement: Format helpers
The project SHALL provide deterministic helpers for CRC32, write-granularity alignment, simple header/blob encoding, status modeling, and image hashing.

项目必须提供 CRC、写粒度对齐、header/blob 编码、状态建模和 image hash 基础能力。

#### Scenario: Corrupted encoded record is rejected
- **WHEN** an encoded record has a mismatched CRC
- **THEN** decoding returns an error instead of silently accepting corrupted data

### Requirement: Unsafe budget for skeleton
The skeleton implementation SHALL keep first-party non-test unsafe usage at 0%.

骨架阶段 first-party 非测试 Rust 代码 unsafe 比例必须为 0%。

#### Scenario: Unsafe scan finds no unsafe
- **WHEN** first-party non-test Rust source is scanned for unsafe usage
- **THEN** no `unsafe` block or `unsafe fn` is present

### Requirement: Deferred compatibility boundary
The project SHALL include an explicit `ffi` boundary module but MUST NOT claim complete C ABI compatibility in this change.

项目可以保留 `ffi` 边界，但本 change 不声明完整 C ABI 兼容。

#### Scenario: FFI boundary is explicit
- **WHEN** a caller looks for C ABI compatibility
- **THEN** the project documents that FFI is deferred and Rust-native APIs are the supported surface for this milestone

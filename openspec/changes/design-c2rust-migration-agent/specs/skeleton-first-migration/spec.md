## ADDED Requirements

### Requirement: Compilable Rust skeleton
The migration system SHALL create a compilable `flashDB_rust` Rust project before function-body migration. The skeleton SHALL include a library crate, a CLI smoke executable, module boundaries, Cargo features, and optional FFI harness boundaries.

系统必须先生成可编译骨架，再逐步填函数体。CLI 只是 smoke/demo，不是核心产品。
#### Scenario: Creating the first Rust project
- **WHEN** the Agent creates `flashDB_rust`
- **THEN** `cargo check` succeeds before migrated function bodies are considered complete
- **THEN** the project exposes a library-first API and a small executable for smoke validation

### Requirement: FlashDB host-verifiable first milestone
The first migration milestone SHALL cover a host-verifiable FlashDB subset: memory backend for deterministic tests, file-mode backend for persistence smoke tests, common public types, error mapping, CRC/util helpers, storage read/write/erase semantics, KVDB set/get/delete/iterate/reopen, and basic TSDB append/query/count/status paths.

首阶段必须既有内存后端用于快速测试，也有 file-mode 持久化 smoke，不能只做内存模拟。
#### Scenario: Reopening a file-mode database
- **WHEN** the Rust file-mode backend writes KVDB data and reopens the database
- **THEN** the stored values and status metadata remain readable
- **THEN** the behavior is comparable with the C FlashDB file-mode oracle

### Requirement: Deferred platform scope
The first milestone MUST NOT require full FAL, raw flash hardware ports, RTOS/Zephyr integrations, complete macro configuration matrices, all C samples, or full C ABI compatibility.

第一阶段不承诺硬件 port、RTOS、Zephyr、全平台宏矩阵和完整 C ABI。
#### Scenario: Encountering hardware-specific code
- **WHEN** the C source references FAL, RTOS, Zephyr, or hardware-specific flash code
- **THEN** the Agent records it as deferred scope
- **THEN** the first milestone continues through host memory/file backends

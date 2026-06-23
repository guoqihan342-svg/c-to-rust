## ADDED Requirements

### Requirement: Compilable Rust skeleton
The migration system SHALL create a compilable `flashDB_rust` Rust project before function-body migration. The skeleton SHALL include a library crate, a CLI smoke executable, module boundaries, Cargo features, and optional FFI harness boundaries.

绯荤粺蹇呴』鍏堢敓鎴愬彲缂栬瘧楠ㄦ灦锛屽啀閫愭濉嚱鏁颁綋銆侰LI 鍙槸 smoke/demo锛屼笉鏄牳蹇冧骇鍝併€?
#### Scenario: Creating the first Rust project
- **WHEN** the Agent creates `flashDB_rust`
- **THEN** `cargo check` succeeds before migrated function bodies are considered complete
- **THEN** the project exposes a library-first API and a small executable for smoke validation

### Requirement: FlashDB host-verifiable first milestone
The first migration milestone SHALL cover a host-verifiable FlashDB subset: memory backend for deterministic tests, file-mode backend for persistence smoke tests, common public types, error mapping, CRC/util helpers, storage read/write/erase semantics, KVDB set/get/delete/iterate/reopen, and basic TSDB append/query/count/status paths.

棣栭樁娈靛繀椤绘棦鏈夊唴瀛樺悗绔敤浜庡揩閫熸祴璇曪紝涔熸湁 file-mode 鎸佷箙鍖?smoke锛屼笉鑳藉彧鍋氬唴瀛樻ā鎷熴€?
#### Scenario: Reopening a file-mode database
- **WHEN** the Rust file-mode backend writes KVDB data and reopens the database
- **THEN** the stored values and status metadata remain readable
- **THEN** the behavior is comparable with the C FlashDB file-mode oracle

### Requirement: Deferred platform scope
The first milestone MUST NOT require full FAL, raw flash hardware ports, RTOS/Zephyr integrations, complete macro configuration matrices, all C samples, or full C ABI compatibility.

绗竴闃舵涓嶆壙璇虹‖浠?port銆丷TOS銆乑ephyr銆佸叏骞冲彴瀹忕煩闃靛拰瀹屾暣 C ABI銆?
#### Scenario: Encountering hardware-specific code
- **WHEN** the C source references FAL, RTOS, Zephyr, or hardware-specific flash code
- **THEN** the Agent records it as deferred scope
- **THEN** the first milestone continues through host memory/file backends

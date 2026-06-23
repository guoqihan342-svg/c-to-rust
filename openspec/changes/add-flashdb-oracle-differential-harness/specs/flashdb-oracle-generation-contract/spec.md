## ADDED Requirements

### Requirement: Fixed FlashDB source baseline
The C oracle generation contract SHALL bind oracle generation to FlashDB commit `93d175549da579b8abac07bd175ce4c3f9dde829` unless a later OpenSpec change updates the baseline.

C oracle 生成必须绑定固定 FlashDB 源码版本，避免 oracle 随上游漂移。

#### Scenario: Oracle contract names source commit
- **WHEN** an operator reads the C oracle contract
- **THEN** it identifies the FlashDB repository URL and exact source commit

### Requirement: C toolchain detection
The oracle generation script SHALL detect whether a usable C compiler and build tools are available before attempting to build the C oracle producer.

脚本必须先检测 C 工具链，不能在缺失工具时产生伪造 oracle。

#### Scenario: Missing C toolchain records skip
- **WHEN** the script runs on a host without a C compiler
- **THEN** it records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not claim C oracle success

### Requirement: C oracle output schema
The C oracle producer SHALL emit the same fixture identity, step ids, operation names, status codes, returned values, and error-code fields expected by the Rust diff command.

C oracle producer 必须输出与 Rust diff 命令兼容的报告 schema。

#### Scenario: Generated oracle can be compared
- **WHEN** a C oracle report is generated for a fixture
- **THEN** the Rust diff command can compare it without schema conversion

### Requirement: CI-compatible producer path
The oracle generation contract SHALL include commands that can run in a Linux or CI environment with `git`, `gcc` or `clang`, and standard shell tools.

oracle 生成契约必须能在 Linux/CI 上执行，而不依赖本机 Windows C 工具链。

#### Scenario: CI invokes producer
- **WHEN** CI has a C compiler available
- **THEN** it can clone or locate FlashDB, build the oracle producer, and produce an oracle report

### Requirement: No local equivalence overclaim
The project MUST NOT report C/Rust semantic equivalence as complete when only the Rust replay consumer has run and the C oracle producer was skipped.

只运行 Rust consumer 时不能声称 C/Rust 等价完成。

#### Scenario: Local C producer skipped
- **WHEN** local verification skips C oracle generation because no C toolchain is installed
- **THEN** the evidence ledger distinguishes Rust replay pass from C oracle comparison pass

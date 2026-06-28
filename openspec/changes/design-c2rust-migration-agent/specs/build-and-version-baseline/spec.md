## ADDED Requirements

### Requirement: Source and toolchain baseline
The migration system SHALL pin every migration run to exact source and toolchain versions. The baseline record MUST include the C source commit, OpenSpec version, Rust toolchain, C2Rust package or artifact hash, C2Rust generation command, LLVM/clang AST frontend configuration, test tool versions, and generated artifact hashes. `LIBCLANG_PATH` is recorded only as ignored diagnostic metadata unless a future explicit libclang adapter is enabled.

每次迁移必须锁定版本，禁止只写 latest。FlashDB 的 GitCode 源码 commit、工具链、C2Rust 产物和测试种子都必须可复现。
#### Scenario: Capturing FlashDB baseline
- **WHEN** the Agent starts the FlashDB migration
- **THEN** it records the FlashDB source commit from `https://gitcode.com/xwxf/FlashDB.git`
- **THEN** it records OpenSpec, Rust, C2Rust, LLVM/clang AST frontend, and test tool versions
- **THEN** it saves `compile_commands.json`, macro matrix, feature matrix, and test seeds

### Requirement: C2Rust baseline is oracle-only
The migration system SHALL use C2Rust output only as a baseline, ABI/layout reference, or oracle. The final `flashDB_rust` project MUST NOT directly ship raw C2Rust output as the completed Rust implementation.

C2Rust 只能作为 baseline/oracle，不能作为最终交付代码。
#### Scenario: C2Rust output is generated
- **WHEN** C2Rust successfully generates Rust from FlashDB build commands
- **THEN** the Agent stores the generated output and hash as baseline evidence
- **THEN** the final safe Rust implementation is still produced through skeleton-first migration, tests, equivalence gates, and unsafe auditing

### Requirement: Baseline fallback
The migration system SHALL fall back to the original C implementation as oracle when C2Rust baseline generation is unavailable or not reproducible.

当 C2Rust 在 Windows 或当前环境不可复现时，必须降级使用原 C 实现作为 oracle。
#### Scenario: C2Rust cannot run locally
- **WHEN** C2Rust cannot run because of platform, LLVM, or toolchain constraints
- **THEN** the Agent records the failure reason
- **THEN** the Agent uses the original C FlashDB implementation as the semantic oracle
- **THEN** the run remains valid only if C/Rust differential tests still execute

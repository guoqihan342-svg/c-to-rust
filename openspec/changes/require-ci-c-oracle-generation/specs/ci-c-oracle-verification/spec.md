## ADDED Requirements

### Requirement: CI configures C oracle producer
The GitHub Actions workflow SHALL configure `FLASHDB_C_ORACLE_PRODUCER` to the repository C oracle generation script when running Ubuntu verification.

CI 必须默认配置 C oracle producer，不能只留下未配置的可选入口。

#### Scenario: Workflow invokes configured producer
- **WHEN** the Ubuntu verification job runs
- **THEN** `scripts/verify-ci.sh` receives `FLASHDB_C_ORACLE_PRODUCER=./oracle/generate_c_oracle.sh`

### Requirement: Configured producer failure fails CI
The CI verification script SHALL fail the job when `FLASHDB_C_ORACLE_PRODUCER` is configured and the producer exits non-zero.

配置了 producer 后，C oracle 失败必须让 CI 失败，不能被忽略。

#### Scenario: Producer exits non-zero
- **WHEN** the configured C oracle producer fails
- **THEN** `scripts/verify-ci.sh` exits non-zero after writing failure evidence

### Requirement: Missing C compiler is explicit skip
The CI verification script MAY skip C oracle generation only when no C compiler is available, and it SHALL write explicit skip evidence.

只有缺少 C 编译器时才允许跳过 C oracle。

#### Scenario: GCC missing
- **WHEN** no usable C compiler is found
- **THEN** the evidence contains `SKIPPED_C_ORACLE_NO_GCC`

### Requirement: C oracle success evidence
When the C oracle producer runs successfully, the CI verification script SHALL record `C_ORACLE_PRODUCER_PASSED` with the oracle report hash.

C oracle 成功必须有机器可读证据。

#### Scenario: Producer succeeds
- **WHEN** the configured C oracle producer writes its report
- **THEN** the evidence contains `C_ORACLE_PRODUCER_PASSED` and the oracle report hash

### Requirement: Equivalence boundary remains explicit
The evidence SHALL NOT label C oracle generation alone as complete C/Rust semantic equivalence.

生成 C oracle 不等于 C/Rust 完整语义等价。

#### Scenario: Only producer passed
- **WHEN** CI has built and run the C oracle producer but no schema-compatible C/Rust diff has passed
- **THEN** the evidence labels the result as C oracle generation, not full equivalence

## ADDED Requirements

### Requirement: Machine-verifiable equivalence
The migration system SHALL prove semantic equivalence with machine-verifiable evidence. LLM judgment MUST NOT be accepted as equivalence evidence.

璇箟绛変环蹇呴』闈犳満鍣ㄨ瘉鎹紝涓嶆帴鍙椻€滄ā鍨嬭涓虹瓑浠封€濄€?
#### Scenario: Verifying a migrated KVDB path
- **WHEN** KVDB set/get/delete/iterate/reopen is migrated
- **THEN** the Agent compares Rust behavior against C FlashDB or C2Rust baseline using the same operation sequence
- **THEN** return codes, read values, error mappings, flash image bytes, and reopen state match or have documented accepted mappings

### Requirement: Rust test generation
The migration system SHALL generate Rust unit tests, integration tests, and differential tests covering the main FlashDB paths. Generated tests MUST include success, boundary, error, GC/reopen, corrupted image, and persistence scenarios.

娴嬭瘯蹇呴』鐢?Rust 涓绘祦娴嬭瘯妗嗘灦锛屽苟瑕嗙洊涓诲共璺緞鍜岃竟鐣?閿欒璺緞銆?
#### Scenario: Generating main-path tests
- **WHEN** a migration slice is completed
- **THEN** the Agent creates or updates Rust tests for the slice
- **THEN** `cargo test` and `cargo nextest run` include those tests in verification

### Requirement: Extended verification gates
The migration system SHALL support coverage, property testing, fuzzing, and performance smoke gates for migrated code. Coverage SHOULD use `cargo llvm-cov nextest`, property tests SHOULD use `proptest`, fuzzing SHOULD use `cargo-fuzz`, and performance smoke SHOULD use Criterion or equivalent Rust benchmarks.

闄ゆ櫘閫氭祴璇曞锛岃繕蹇呴』瑙勫垝瑕嗙洊鐜囥€佹€ц川娴嬭瘯銆乫uzz 鍜屾€ц兘 smoke 闂ㄧ銆?
#### Scenario: Validating persistent storage formats
- **WHEN** header, blob, sector status, CRC, or alignment logic is migrated
- **THEN** the Agent validates golden layout fixtures and corrupted-image cases
- **THEN** failing examples are minimized and added to regression tests

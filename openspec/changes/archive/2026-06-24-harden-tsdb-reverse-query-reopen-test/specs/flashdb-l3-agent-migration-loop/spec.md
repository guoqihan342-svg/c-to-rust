## ADDED Requirements

### Requirement: TSDB Reverse Query Reopen Test Evidence Hardening
The system SHALL assert that the `tsdb-reverse-query-reopen` Rust replay test validates the reopen operation report as an explicit successful step.

系统必须确保 `tsdb-reverse-query-reopen` Rust replay 测试把 reopen 操作报告校验为明确成功的 step。

#### Scenario: Reopen step report fields are asserted
- **WHEN** `l3-tsdb-reverse-query-reopen.json` is replayed by the Rust test
- **THEN** step `ts-rqr-006` is asserted to contain `op:"ts.reopen"`, `status:"ok"`, `code:"OK"`, and an `image_hash` field

#### Scenario: Reopen hash remains metadata
- **WHEN** the test checks `ts-rqr-006`
- **THEN** it asserts the presence of `image_hash` without pinning a concrete hash value

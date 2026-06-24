## ADDED Requirements

### Requirement: TSDB Set Status Report Schema Repair
The system SHALL emit unambiguous replay report fields for successful TSDB `ts.set_status` operations.

系统必须为成功的 TSDB `ts.set_status` 操作输出无歧义的 replay 报告字段。

#### Scenario: Successful set status separates step and TS status
- **WHEN** a replay fixture executes a successful `ts.set_status` operation
- **THEN** the step execution status is reported as `status:"ok"` and the requested TS business status is reported as `ts_status`

#### Scenario: Successful set status report has no duplicate status key
- **WHEN** Rust replay or the C oracle emits a successful `ts.set_status` step
- **THEN** the emitted step JSON contains exactly one step-level `status` key and does not use a second `status` key for the TS business status

### Requirement: TSDB Set Status Schema Diff Parity
The system SHALL compare repaired Rust and C oracle `ts.set_status` reports using the same schema-aware diff gate.

系统必须使用同一个 schema-aware diff 门禁比较修复后的 Rust 与 C oracle `ts.set_status` 报告。

#### Scenario: Repaired schema participates in behavior diff
- **WHEN** Rust and C oracle reports include a successful `ts.set_status` step
- **THEN** `ts_status` is treated as a behavior field and is not hidden by accepted metadata differences

#### Scenario: Mutated TS status is rejected
- **WHEN** a report mutates a successful `ts.set_status` step from one `ts_status` value to another
- **THEN** schema-aware diff fails at the mutated `ts_status` field path

### Requirement: TSDB Set Status Schema Repair Evidence
The system SHALL persist evidence for the TSDB `ts.set_status` report-schema repair.

系统必须持久化 TSDB `ts.set_status` report-schema 修复证据。

#### Scenario: Evidence records repair scope and validation
- **WHEN** the schema repair is implemented
- **THEN** evidence under `validation/evidence/flashdb/` records TDD red/green results, Rust replay output, C oracle output, schema diff, negative diff, unsafe scan, performance smoke, OpenSpec validation, and git whitespace validation

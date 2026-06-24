## Why

TSDB `ts.set_status` 的成功 replay 报告当前同时使用两个 `status` key：一个表示 step 执行状态，另一个表示业务 TS 状态。重复 key 会让 JSON 消费者、schema-aware diff 和后续 C/Rust 语义证据产生歧义。

The TSDB `ts.set_status` success replay report currently emits two `status` keys: one for step execution status and one for the business TS status. Duplicate keys make JSON consumers, schema-aware diff, and later C/Rust semantic evidence ambiguous.

## What Changes

- 将成功 `ts.set_status` 报告中的业务 TS 状态字段改为 `ts_status`，保留 step 执行状态字段 `status`。
- 同步 Rust replay、C oracle 输出和 fixture expected report，保持 C/Rust 报告 schema 一致。
- 新增/更新 Rust 测试，先证明旧重复 key 形态会失败，再证明新 `ts_status` schema 通过。
- 生成本切片的证据文件，记录 TDD 红绿、schema diff、unsafe、性能烟测和最终验证。
- 不改 TSDB 存储语义、FlashDB C 原生语义、字段值含义或差分 allowlist 的行为字段保护。

## Capabilities

### New Capabilities

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: 修复 TSDB `ts.set_status` replay 报告 schema，使 step status 与 TS business status 明确分离。

## Impact

- `flashDB_rust/src/replay.rs`: Rust replay 报告字段名从 duplicate `status` 修为 `ts_status`。
- `flashDB_rust/oracle/flashdb_c_oracle.c`: C oracle `ts.set_status` 成功输出同步为 `ts_status`。
- `flashDB_rust/fixtures/*.expected.json`、`flashDB_rust/tests/`: 更新预期样例和 schema 断言。
- `validation/evidence/flashdb/`: 新增 `tsdb-set-status-schema` 相关证据。
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md`: 归档时追加 schema repair 要求。

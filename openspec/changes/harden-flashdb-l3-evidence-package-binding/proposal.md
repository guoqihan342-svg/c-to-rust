## Why

当前 `validate_flashdb_l3_evidence.py` 已要求 FlashDB L3 package 中存在 diff、final verification 等文件，但主要信任 summary 中的状态字段。若底层 `*-diff.json` 或 `*-final-verification.json` 漂移为失败，summary 仍可能让 package 看起来可消费，削弱 L3 语义等价证据闭环。

## What Changes

- 收紧 FlashDB L3 evidence package validator：必须读取并验证正向 diff 报告、final verification 报告和 summary evidence hash。
- 正向 diff 必须明确 `status=passed` 且没有 `first_mismatch`。
- final verification 必须明确 `status=passed`，并且其中的 diff、C oracle toolchain、checks 不能含失败状态。
- 若 summary 记录 evidence 文件的 `sha256`，validator 必须与实际文件 hash 对齐。
- 增加负向单测，证明 diff 失败、final verification 失败、summary hash 漂移会被拒绝。

## Capabilities

### New Capabilities
- `flashdb-l3-evidence-package-binding`: 约束 FlashDB L3 validator 不只检查 evidence 文件存在，还要检查关键 evidence 内容与 summary 绑定一致。

### Modified Capabilities
- None.

## Impact

- Affected validator: `validation/tools/validate_flashdb_l3_evidence.py`.
- Affected tests: `validation/tools/test_validate_flashdb_l3_evidence.py`.
- Affected docs/gates: `validation/gates.md`, this OpenSpec change.
- Dependencies: no new third-party dependency; uses existing Python stdlib hashing and JSON parsing.

英文镜像见 `2026-06-27-candidate-route-p0.en.md`。

# Candidate Route P0 Plan - Superseded

> **SUPERSEDED / DO NOT IMPLEMENT.**
>
> 中文：本文件是历史计划索引，不再是可执行开发计划。不要按旧步骤恢复
> `DeprecatedLegacyCrc32`、`LegacyCrc32Emitter`、`LEGACY_CRC32_DELETE_WHEN`、
> typed IR crc32 matcher、typed IR canned emitter、string translator crc32 byte-cursor
> recognizer 或 `crc32_update_byte()` canned template。
>
> English: This file is a historical plan index, not an executable implementation
> plan. Do not restore `DeprecatedLegacyCrc32`, `LegacyCrc32Emitter`,
> `LEGACY_CRC32_DELETE_WHEN`, any typed IR crc32 matcher, any typed IR canned
> emitter, the string-translator crc32 byte-cursor recognizer, or the
> `crc32_update_byte()` canned template.

## Current Contract / 当前约束

- 当前 typed IR candidate route 只有两类：`GenericTypedIr` 和 `Unsupported`。
- The current typed IR candidate routes are only `GenericTypedIr` and
  `Unsupported`.
- `CandidateRouteDecision` 只描述候选生成 provenance，不决定 `semantic_pass`。
- `CandidateRouteDecision` records candidate-generation provenance only; it does
  not decide `semantic_pass`.
- `semantic_pass=false` 和 `generated_draft_semantic_pass=false` 必须保持不变，
  除非后续独立 validation gates 显式接受 exact generated draft。
- `semantic_pass=false` and `generated_draft_semantic_pass=false` must remain
  unchanged unless later independent validation gates explicitly accept the exact
  generated draft.
- FlashDB crc32 只是一个验证用例；不要为 FlashDB 增加新的专用 route 或模板。
- FlashDB crc32 is only a validation use case; do not add a new FlashDB-specific
  route or template.

## Authoritative References / 权威参考

- `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
- `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`
- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- `CONTEXT.md` sections 77, 81, and later entries

## Next Work / 后续工作

1. 继续扩展 generic typed IR 覆盖面，例如标量二元运算、clang-lowered 表达式和受限控制流。
2. 对真实 FlashDB `real-fdb-calc-crc32` 补完整 generated-draft validation gates：
   C oracle、Rust replay、schema diff、negative diff、unsafe ledger、final verification。
3. 保留 raw string crc32 byte-cursor fail-closed 回归，防止 canned template 回流。

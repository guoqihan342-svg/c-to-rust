## Why

Some early OpenSpec change specs contain mojibake in Chinese explanatory prose. The parser anchors still validate, but the artifacts are not durable bilingual documentation for future agents.

部分早期 OpenSpec change spec 的中文说明出现乱码。虽然 parser anchors 仍可通过校验，但这些文件已经不能作为后续 Agent 可读、可追踪的中英文文档。

## What Changes

- Add a small L3 documentation-quality requirement that bilingual OpenSpec prose must remain readable UTF-8 while parser-required anchors stay unchanged.
- Repair mojibake in the early `design-c2rust-migration-agent` delta spec files.
- Preserve requirement names, `Scenario`, `WHEN`, `THEN`, and task checkbox syntax.
- Add scan evidence showing the issue before and after repair.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add a documentation integrity gate for L3 OpenSpec artifacts.

## Impact

- OpenSpec docs only; no Rust runtime behavior, fixture behavior, C oracle behavior, or public API behavior changes.
- Affects early change artifacts under `openspec/changes/design-c2rust-migration-agent/specs/`.
- Adds repair evidence under `validation/evidence/flashdb/`.

## Context

The project intentionally keeps repo-facing OpenSpec prose bilingual where useful, while preserving parser-required English anchors such as `## ADDED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, and `THEN`. Earlier artifacts were written before the current UTF-8 discipline was stable, so several Chinese prose lines became mojibake.

本项目要求必要的 OpenSpec 文档保持中英文可读，同时保留 parser 需要的英文结构锚点。早期文档生成时 UTF-8 约束还不稳定，因此部分中文说明变成了乱码。

## Goals / Non-Goals

**Goals:**

- Repair unreadable Chinese prose in early OpenSpec delta specs.
- Keep OpenSpec parser anchors and requirement semantics unchanged.
- Record a repeatable scan command that can catch the same class of issue.
- Keep the change doc-only and low risk.

**Non-Goals:**

- Do not rewrite the agent architecture.
- Do not add new Rust features or tests.
- Do not change FlashDB L3 behavior claims.
- Do not translate parser-required anchors.

## Approach

Use a conservative text scan for known mojibake markers, persist the failing scan output, replace only the damaged prose lines with readable Chinese, then rerun the scan and OpenSpec validation.

使用保守的乱码标记扫描，先持久化失败输出；随后只替换损坏的中文说明行；最后重新运行扫描和 OpenSpec 校验。

## Risks / Trade-offs

- The scan is heuristic and intentionally narrow; it catches the known corruption patterns without flagging legitimate English/OpenSpec syntax.
- The repaired text is explanatory prose. Normative English requirements remain the source of parser-stable behavior.

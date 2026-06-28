# English Mirror:  README

Chinese original: `README.md`.

This file is the English mirror for `README.md`. The Chinese source is the authoritative maintenance document; update this file in the same change whenever the Chinese document changes.

## Scope

This mirror covers the repository overview and quick entry point. It is intentionally concise for older plans, templates, and OpenSpec records so that the repository has a stable bilingual entry point without turning historical artifacts into the active backlog.

## Source Outline

The Chinese source currently contains these major headings:

- `# C-to-Rust Progressive Migration Pipeline`
- `## 愿景`
- `## 架构概览`
- `## L0-L4 验证分层`
- `## 当前状态`
- `## 核心目录`
- `## 待办来源`
- `## OpenCode 比赛单次交互`
- `## 快速命令`
- `# 运行翻译器测试（默认 feature）`
- `# 运行翻译器测试（含 typed IR + clang frontend）`
- `# 运行 auto migration（以 FlashDB crc32 为例）`
- `# 验证自动翻译证据`
- `# 语义通过验证`
- `# 全量回归`
- `## 设计原则`

## Current OpenCode Competition Summary

The Chinese README now treats the 600-minute figure as an optional external evaluation budget, not as an optimization target. The competition path prioritizes accuracy and complete evidence, may process independent slices with parallel agents or batch workers, and requires isolated worker outputs plus common validator/final-verification acceptance.

## Maintenance Notes

- Keep filenames paired as `README.md` and `README.en.md` in the same directory.
- Keep the first line of the Chinese source pointing to `README.en.md` with the repository-standard mirror notice.
- For project-wide priorities, follow `docs/c2rust-migration-agent/future-vision-and-mvp.md`; local plans, OpenSpec tasks, and validation checklists are scoped artifacts only.

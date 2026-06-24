## Why

L1 已证明 15 个复杂 C/C-major 项目的原生 C baseline 可复现，但还不能证明 Rust 迁移能力。现在需要进入 L2/L3，用少量低耦合切片建立可复制的 C oracle、Rust slice、schema diff 和 unsafe ledger 样板。

## What Changes

- 新增一个小型 Rust slice validation crate，覆盖三个已通过 L1 的纯函数/格式切片：
  - SQLite varint encode/decode
  - zlib-ng Adler-32 checksum
  - zstd xxHash32 checksum
- 为每个切片增加 C oracle harness 或 C oracle 生成脚本，并生成 repo-local compact evidence。
- 增加 Rust tests，使用 C oracle fixtures 验证 Rust slice 行为。
- 增加 L2/L3 汇总证据，明确哪些切片 Rust 编译通过、C/Rust diff 通过、unsafe 是否为 0。
- 保持报告边界：这些结论只覆盖命名切片、固定输入域和 pinned upstream commit，不代表完整项目迁移。

## Capabilities

### New Capabilities

- `supercomplex-l2-slice-validation`: 复杂 C 项目的 bounded Rust slice、C oracle fixture、schema-aware diff 和 per-slice evidence。

### Modified Capabilities

None.

## Impact

- Affected areas: `validation/l2_slices/**`, `validation/evidence/**`, scripts for oracle generation, and OpenSpec artifacts.
- External systems: WSL Ubuntu build toolchain and existing L1 upstream clones under `C:\Users\Administrator\Documents\c-to-rust-l1-work`.
- Dependencies: Rust toolchain, C compiler, existing pinned C checkouts for SQLite, zlib-ng, and zstd.
- No FlashDB runtime API changes are expected.

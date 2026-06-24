## Why

Wave2 已经把 catalog 扩展到 40 个复杂 C/C-major 目标，并完成 40/40 L0 remote probe。下一步需要把新增 wave2 目标推进到 L1：真实 clone、pin commit、native C build/test smoke，并保存可审计证据。

## What Changes

- 新增 wave2 L1 native validation runner，用统一 JSON schema 记录 clone/build/smoke 命令、退出码、耗时、日志路径和失败摘要。
- 并行尝试至少 12 个 wave2 项目，覆盖网络/协议、安全/parser、媒体/科学数据、系统/虚拟化等项目族。
- 聚合 worker 结果到 per-project L1 evidence 和 `validation/evidence/l1-native-summary.json`。
- 新增 wave2 L1 summary evidence，明确成功、失败和未尝试项目。
- 保留报告边界：L1 只证明 native C baseline build/test smoke，不证明 Rust 迁移、unsafe 比例、语义等价或性能保持。

## Capabilities

### New Capabilities

- `supercomplex-wave2-l1-native-validation`: 覆盖 wave2 项目的 pinned native C build/test smoke、外部日志、聚合证据和 L1 报告边界。

### Modified Capabilities

- None.

## Impact

- Affected files: `validation/tools/**`, `validation/evidence/**`, `validation/README.md`, and OpenSpec artifacts.
- External systems: GitHub upstream repositories cloned into `C:\Users\Administrator\Documents\c-to-rust-l1-work\wave2-l1`.
- Build runs execute in WSL/Linux and may fail when dependencies are missing; failures are valid L1 evidence if recorded.
- No `flashDB_rust` runtime behavior changes are expected.

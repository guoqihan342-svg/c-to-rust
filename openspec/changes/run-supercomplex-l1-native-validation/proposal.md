## Why

当前 catalog 已经证明 22 个复杂 C/C-major 项目远程可达，但这仍只是 L0。为了把“十几个复杂 C 项目验证”推进到可审计状态，需要对至少 12 个候选项目执行真实的 pinned native C build/test smoke，并把通过、失败和日志路径固化为证据。

## What Changes

- 新增一轮 L1 native validation 证据，记录每个项目的 upstream commit、build/test 命令、退出码、耗时、工具链版本和日志位置。
- 增加聚合证据文件，明确哪些项目 L1 passed、哪些 failed/blocked，以及失败是否由依赖、构建脚本、网络或测试命令导致。
- 保持报告边界：L1 只代表原生 C baseline 可复现，不代表 Rust slice 已编译，也不代表 C/Rust 语义等价。
- 继续保留外部 clone/build 工作区，不把大型上游仓库或 build artifact 放入本仓库。

## Capabilities

### New Capabilities

- `supercomplex-l1-native-validation`: 复杂 C/C-major 项目的 pinned native C build/test smoke 证据、聚合状态和报告边界。

### Modified Capabilities

None.

## Impact

- Affected areas: `validation/evidence/**`, validation documentation, and OpenSpec change artifacts.
- External systems: GitHub upstream repositories cloned into an external WSL workspace under `C:\Users\Administrator\Documents\c-to-rust-l1-work`.
- Dependencies: WSL Ubuntu build toolchain, git, gcc, make, cmake, autotools, perl/python/tcl, and project-specific system libraries.
- No production Rust API changes are expected for this L1 validation change.

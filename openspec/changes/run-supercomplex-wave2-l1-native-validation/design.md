## Context

当前 L1 summary 覆盖 18 个旧项目尝试，其中 15 个通过、3 个失败。Wave2 新增 18 个目标还只有 L0 evidence。用户要求继续验证，因此本 change 进入 L1 native smoke，但仍不做 Rust 迁移或语义等价声明。

L1 构建必须在外部工作区执行，不能把大型 upstream clone、build artifact 或中间产物放入本仓库。仓库只提交 compact JSON evidence 和必要 runner。

## Goals / Non-Goals

**Goals:**

- 尝试至少 12 个 wave2 项目的 native C build/test smoke。
- 每个尝试都记录 pinned commit、命令、退出码、耗时、日志路径、工具链版本和 failure summary。
- 支持并行 worker 分组运行，避免一个项目族阻塞所有验证。
- 聚合 per-project evidence 和 L1 summary。

**Non-Goals:**

- 不要求所有 wave2 项目都 L1 通过。
- 不在本 change 内做 L2 Rust slice 或 L3 C/Rust diff。
- 不安装或修改系统级依赖；缺失依赖按 L1 failure 记录。
- 不提交 upstream clone、build directory 或完整日志。

## Decisions

### Decision 1: Runner 统一证据格式

用一个 Python runner 在 WSL 下执行 clone/build/smoke，生成 `results.json` 和每步日志。这样 worker 只负责项目族执行，主线程负责聚合，不让每个 worker 发明自己的 schema。

### Decision 2: 失败也是证据

L1 要证明 baseline 可复现性。如果 build 失败、缺依赖或测试失败，per-project evidence 仍然提交为 `status: failed`，并记录失败命令和日志路径；不把失败项目从 summary 中隐藏。

### Decision 3: 并行项目族

项目按相对独立的依赖和领域分组：

- network-protocol: HAProxy, memcached, libpcap, tcpdump, OpenVPN
- security-parser: libxml2, wolfSSL, OpenSSH Portable, libgit2
- media-data: x264, HDF5, ImageMagick, MuPDF
- system-virt: Vim, QEMU, systemd, Linux

这四组写入不同外部目录，互不覆盖。

## Risks / Trade-offs

- [Risk] 大型构建时间长。Mitigation: 每步设置 timeout，允许记录 timeout failure。
- [Risk] WSL 缺依赖导致失败。Mitigation: 不临时 apt install；记录缺失命令和日志，后续可开依赖补齐 change。
- [Risk] 多 worker 竞争 CPU/IO。Mitigation: smoke 命令使用小并行度，项目族目录隔离。
- [Risk] GitHub branch HEAD 会变化。Mitigation: 每次 clone 后记录 actual commit SHA。

## Migration Plan

1. 创建 OpenSpec artifacts 并验证。
2. 增加 wave2 L1 runner。
3. 并行执行项目族 worker。
4. 聚合 worker `results.json` 到 repo-local evidence。
5. 更新 `l1-native-summary.json` 和 README。
6. 运行 OpenSpec、Rust tests、catalog validation 和 diff hygiene。
7. Commit and push.

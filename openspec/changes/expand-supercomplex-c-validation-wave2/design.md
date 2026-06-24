## Context

当前仓库已有 22 个复杂 C/C-major catalog 目标，并有 18 个项目的 L1 native smoke 尝试证据，其中 15 个通过。用户要求继续“找十几个超级复杂的 C 项目进行验证”，这次应扩展候选面并形成可审计 L0 证据，但不能把远程 HEAD 探测包装成构建或迁移完成。

现有 `scripts/validate-c-project-catalog.ps1` 强制 `repo_url` 为 GitHub HTTPS `.git` URL，并能用 `git ls-remote --symref` 检查默认分支。为了保持小而精和快速闭环，本 change 继续复用这个规则。

## Goals / Non-Goals

**Goals:**

- 新增至少 18 个 wave2 超复杂 C/C-major 候选项目。
- 新候选覆盖内核/虚拟化、系统服务、网络安全、图形文档、科学数据、协议和服务端基础设施。
- 每个新增目标必须有 repo URL、默认分支、复杂度信号、native build smoke、test smoke、L2 迁移切片、oracle strategy、performance smoke 和风险说明。
- 重新生成离线 catalog 校验和远程 HEAD/default-branch probe 证据。
- 明确报告边界：L0 只证明 catalog 和远程可达，不证明 L1/L2/L3。

**Non-Goals:**

- 不克隆或构建所有新增大型上游仓库。
- 不放宽当前 catalog 验证器的 GitHub URL 规则。
- 不对新增项目声明 Rust 迁移、unsafe 比例、语义等价或性能保持。

## Decisions

### Decision 1: 先扩 GitHub 可验证目标

选择 GitHub 上可直接通过当前验证器的目标，例如 Linux mirror、QEMU mirror、systemd、HAProxy、OpenSSH、Suricata、HDF5、MuPDF 等。GitLab、Sourceware、Savannah 的官方上游先不纳入本次 catalog，以免需要同时改验证器 schema 和远程探测策略。

Alternative considered: 同时支持 GitLab/Sourceware/Savannah。Rejected for this change because it would mix target discovery with validator behavior changes and slow down delivery.

### Decision 2: L0 证据优先，L1 分批执行

新增项目体量很大，像 Linux、QEMU、systemd、MariaDB、ImageMagick 和 MuPDF 的 clone/build/test 都可能很慢。先用 L0 证明候选质量和远程可达，再由后续 L1 change 按项目族分配 worker 到外部工作区。

Alternative considered: 立即对所有新增项目执行 L1 build/test。Rejected because one turn would become many unrelated dependency failures, and failures would be harder to审计。

### Decision 3: 每个新增项目必须给出 L2 切片入口

catalog 不是泛泛项目清单。每个目标都必须给出较小、可构造 C oracle 的 L2 候选切片，例如 parser、checksum、metadata、format header、buffer helper、wire-format helper 或单个工具函数族。

## Risks / Trade-offs

- [Risk] GitHub mirror 与项目官方上游可能存在滞后。Mitigation: evidence 记录 HEAD SHA；需要官方上游时通过后续 change 支持非 GitHub URL。
- [Risk] 新增目标过多会提高维护成本。Mitigation: 保持字段结构一致，并通过 validator 检查唯一性、必填字段和 default branch。
- [Risk] 用户可能误解 L0 为迁移验证完成。Mitigation: README、evidence 和 summary 都保留 non-equivalence boundary。
- [Risk] 一些候选是 C/C++ major 而非纯 C。Mitigation: 只要目标切片是 C-owned，catalog 使用 `language_profile` 明确标注。

## Migration Plan

1. 创建 OpenSpec artifacts 并通过 strict validation。
2. 扩展 `validation/projects.json` 到至少 40 个目标。
3. 更新 README 目标数、L1 summary 的 catalog count 和未尝试列表。
4. 更新 project cards，加入 wave2 优先级和项目卡片。
5. 运行离线 catalog 验证。
6. 运行远程 HEAD/default-branch probe。
7. 运行 OpenSpec、FlashDB Rust、L2 slice、diff hygiene 验证。
8. Commit and push.

## Open Questions

- 后续是否放宽 catalog validator 以支持 GitLab、Sourceware、Savannah 等官方上游 URL？
- L1 wave2 是否优先跑 `haproxy`、`openssh-portable`、`libxml2`、`hdf5`、`mupdf` 这类依赖相对可控项目，还是先跑 Linux/QEMU/systemd 作为压力上限？

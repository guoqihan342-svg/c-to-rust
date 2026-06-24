## Why

上一轮已经把 catalog 扩到 22 个复杂 C/C-major 目标，并对其中 18 个做过 L1 native smoke 尝试。用户继续要求“找十几个超级复杂的 C 项目进行验证”，因此需要新增一批更高复杂度、更广领域的候选，并先固化可审计的 L0 远程验证证据。

## What Changes

- 将 `validation/projects.json` 从 22 个目标扩展到至少 40 个目标。
- 新增 wave2 候选，覆盖内核/虚拟化、系统服务、网络安全、图形文档、科学数据和协议基础设施。
- 继续使用现有 GitHub `.git` URL catalog 校验规则，先不混入 GitLab、Sourceware、Savannah 等非 GitHub 上游，以免破坏当前验证器。
- 重新生成离线 catalog 校验和远程 HEAD/default-branch probe 证据。
- 更新 README、project cards 和 L1 summary 边界，使新增目标可进入后续 L1/L2 任务。
- 明确本 change 只声明 L0 catalog/remote probe 通过，不声明新增项目已经完成 L1 build、Rust 迁移或语义等价。

## Capabilities

### New Capabilities

- `supercomplex-c-validation-wave2`: 覆盖 wave2 新增超级复杂 C/C-major 项目 catalog、L0 远程验证、后续 L1/L2 验证入口和报告边界。

### Modified Capabilities

- None.

## Impact

- Affected files: `validation/projects.json`, `validation/README.md`, `validation/l1-l2-project-cards.md`, `validation/evidence/catalog-validation.json`, `validation/evidence/catalog-remote-probe.json`, and OpenSpec artifacts.
- External systems: GitHub upstream repositories are probed with `git ls-remote --symref <repo> HEAD`.
- No large upstream repositories are cloned into this repo.
- No FlashDB runtime or `flashDB_rust` behavior changes are expected.

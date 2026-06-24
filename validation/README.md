# Multi-Project C-to-Rust Validation

中文：本目录用于管理“十几个复杂 C 项目”的迁移验证候选集。当前阶段已完成 L0 目录校验、远程 HEAD 探测，以及 40/40 个项目的 L1 native C build/test smoke 尝试；这仍不代表这些项目已经迁移成功，也不代表语义等价已经证明。

English: this directory tracks candidate projects for broader C-to-Rust migration validation. The current milestone proves L0 catalog validity, remote HEAD reachability, and 40/40 L1 native C build/test smoke attempts; it does not claim migration success or semantic equivalence for the listed projects.

## Files

- `projects.json`: versioned catalog of complex C/C-major validation targets.
- `gates.md`: L0-L3 validation gates and evidence requirements.
- `evidence/catalog-validation.json`: latest offline catalog validation report.
- `evidence/catalog-remote-probe.json`: latest optional remote HEAD probe report.
- `evidence/l1-native-summary.json`: latest compact L1 native C build/test smoke summary.
- `evidence/wave2-l1-native-summary.json`: compact L1 summary for the 18 wave2 targets.
- `evidence/remaining-l1-native-summary.json`: compact L1 summary for the final 4 catalog targets that previously had no L1 attempt.
- `evidence/l1-failure-classification.json`: machine-readable classification for failed L1 attempts.
- `evidence/l1-failure-classification.md`: reviewer-friendly failed L1 classification summary.

## Fast Commands

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1 -ProbeRemote
```

The verifier is intentionally lightweight. It does not clone large repositories. Future per-project changes must pin commits, clone outside this repository, run the native C build/test smoke, define a bounded migration slice, and add C/Rust differential evidence before claiming deeper success.

## Current Candidate Count

The catalog currently contains 40 targets across database/storage, networking, crypto, media, runtime, allocator, image/codec, terminal/system, kernel/virtualization, document processing, scientific data, VPN, packet analysis, and embedded domains.

## Wave2 Boundary

中文：Wave2 增加了 18 个 GitHub 可达的超复杂 C/C-major 目标。本轮已经对 18/18 个 wave2 目标执行 L1 native C build/test smoke：8 个通过，10 个失败，失败项目仍作为可审计 evidence 保留。L1 只证明 pinned native C baseline 的构建/烟测尝试，不证明 Rust 迁移、unsafe 预算、性能保持或 C/Rust 语义等价。

English: Wave2 adds 18 GitHub-reachable super-complex C/C-major targets. This round attempted L1 native C build/test smoke for 18/18 wave2 targets: 8 passed and 10 failed, with failures preserved as auditable evidence. L1 only proves pinned native C baseline build/smoke attempts; it does not prove Rust migration, unsafe budget, performance preservation, or C/Rust semantic equivalence.

## Full L1 Attempt Boundary

中文：当前 40 个 catalog 目标都已经有 L1 native C build/test smoke 尝试证据：23 个通过，17 个失败，`not_attempted_catalog_projects` 为空。失败项目仍保留为可审计 evidence，后续若要提升通过率，应针对失败命令和依赖开独立修复 change。

English: all 40 catalog targets now have L1 native C build/test smoke attempt evidence: 23 passed and 17 failed, with an empty `not_attempted_catalog_projects` list. Failed projects remain auditable evidence; improving their pass rate should be handled through separate changes focused on the failed commands and dependencies.

## L1 Failure Classification

中文：17 个 L1 failed 项目已经完成诊断分类。主要类别包括缺少开发包、缺少构建工具、git checkout 需要 bootstrap/autogen、构建配方冲突、环境限制、clone/network failure、timeout、evidence gap 等。该分类只用于决定后续修复顺序，不会把失败项目改为通过。

English: the 17 failed L1 projects have diagnostic classifications. Major categories include missing development packages, missing build tools, git-checkout bootstrap requirements, build recipe conflicts, environment restrictions, clone/network failure, timeout, and evidence gaps. The classification is only for remediation planning; it does not convert failed projects to passed.

## Non-Equivalence Boundary

Passing catalog validation means only:

- the catalog schema is valid,
- each target has required migration metadata,
- target ids are unique,
- optional remote probes can reach upstream HEADs when enabled.

It does not mean:

- the original C project builds locally,
- any Rust translation compiles,
- unsafe ratio is below the project budget,
- C/Rust behavior is equivalent,
- performance is preserved.

Those claims require L1-L3 evidence described in `gates.md`.

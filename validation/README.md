# Multi-Project C-to-Rust Validation

中文：本目录用于管理“十几个复杂 C 项目”的迁移验证候选集。当前阶段只完成 L0 目录校验和远程 HEAD 探测，不代表这些项目已经迁移成功，也不代表语义等价已经证明。

English: this directory tracks candidate projects for broader C-to-Rust migration validation. The current milestone only proves L0 catalog validity and remote HEAD reachability; it does not claim migration success or semantic equivalence for the listed projects.

## Files

- `projects.json`: versioned catalog of complex C/C-major validation targets.
- `gates.md`: L0-L3 validation gates and evidence requirements.
- `evidence/catalog-validation.json`: latest offline catalog validation report.
- `evidence/catalog-remote-probe.json`: latest optional remote HEAD probe report.

## Fast Commands

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1 -ProbeRemote
```

The verifier is intentionally lightweight. It does not clone large repositories. Future per-project changes must pin commits, clone outside this repository, run the native C build/test smoke, define a bounded migration slice, and add C/Rust differential evidence before claiming deeper success.

## Current Candidate Count

The catalog currently contains 22 targets across database/storage, networking, crypto, media, runtime, allocator, image/codec, terminal/system, RTOS, and embedded domains.

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

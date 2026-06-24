## Context

The active broader goal is to validate the migration approach against more than one FlashDB-sized target. FlashDB now has a Rust skeleton, C oracle generation, schema-aware C/Rust diff, and CI evidence, but it is still a single embedded database project.

本 change 的目标是把“十几个复杂 C 项目验证”落成可执行的第一步：候选目录、gate 定义、轻量远程探测、证据 JSON。它不下载大仓库，也不声明任何项目已经完整迁移。

## Goals / Non-Goals

**Goals:**

- Maintain a checked-in catalog of at least 12 complex C/C-major repositories.
- Cover diverse project shapes so future migration work exercises build systems, C APIs, macro-heavy code, generated sources, platform abstractions, and long-running test suites.
- Provide a fast no-clone verifier for catalog schema, uniqueness, required fields, gate definitions, and optional `git ls-remote` reachability.
- Write durable evidence so later agents can compare catalog drift and default-branch movement.
- Keep the milestone small, safe, and token-efficient.

**Non-Goals:**

- This change does not clone, build, or migrate every project.
- This change does not promise that arbitrary C projects can be converted automatically.
- This change does not add heavy dependencies, graph databases, container orchestration, or CI network gates for all external repositories.
- This change does not change the FlashDB Rust runtime.

## Decisions

### Decision 1: Catalog before cloning

Start with a structured catalog and no-clone remote probes. The candidate set is large enough that full clone/build/migration in one change would be slow, brittle, and hard to audit.

Alternative considered: immediately clone and build all projects. Rejected because large projects such as FFmpeg, PostgreSQL, OpenSSL, Git, and Redis require different toolchains and would turn one milestone into many unrelated failures.

### Decision 2: L0-L3 gates

Use four validation levels:

- L0: catalog schema and remote repository HEAD probe.
- L1: native C build/test smoke in an isolated external workspace.
- L2: bounded migration slice with generated Rust compiling and unsafe accounting.
- L3: C/Rust oracle or golden-test differential evidence plus performance smoke.

This prevents a shallow probe from being reported as semantic equivalence.

### Decision 3: PowerShell verifier first

Use PowerShell because the user is on Windows and the repo is actively operated from PowerShell. Keep the script dependency-free and optional-network; `-ProbeRemote` is explicit.

Alternative considered: add a Rust verifier crate. Rejected for this milestone because the script only validates JSON shape and calls `git ls-remote`; adding a Rust tool would add maintenance without improving evidence quality.

### Decision 4: Catalog fields are migration-oriented

Each target records domain, repository URL, expected branch, complexity signals, build smoke command, test smoke command, migration slice, oracle strategy, performance smoke, and risk notes. This gives future agents concrete entry points instead of generic project names.

### Decision 5: CI should not depend on external project availability yet

The verifier can be run locally with `-ProbeRemote`, but GitHub CI should not fail on transient external network or upstream default-branch movement until each target gets a pinned per-project change.

## Risks / Trade-offs

- [Risk] Default branches and HEAD SHAs drift. -> Mitigation: evidence records probe timestamp and observed SHA; future deep validation must pin commits.
- [Risk] Catalog entries may be too broad. -> Mitigation: each entry includes a bounded migration slice and first oracle strategy.
- [Risk] Network probes can be flaky. -> Mitigation: remote probing is explicit and writes failure details instead of hiding them.
- [Risk] “Catalog passed” may be mistaken for “migration passed”. -> Mitigation: docs and spec state L0 is not semantic equivalence.
- [Risk] Some projects are not pure C. -> Mitigation: catalog allows C-major projects when the target slice is C-owned and build/test smoke is explicit.

## Migration Plan

1. Add this OpenSpec change.
2. Add `validation/projects.json` with at least 12 complex C/C-major targets.
3. Add `validation/README.md` and `validation/gates.md`.
4. Add `scripts/validate-c-project-catalog.ps1`.
5. Run catalog validation without network.
6. Run optional remote probe and write evidence.
7. Validate OpenSpec and git diff.
8. Push after local verification.

Future changes should pick one target or one family at a time, pin a commit, clone outside the repo, run L1 build/test smoke, define an L2 migration slice, and only then add C/Rust differential evidence.

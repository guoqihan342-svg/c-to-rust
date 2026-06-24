## Context

The repository already has an L0 catalog of 22 complex C/C-major projects and remote HEAD evidence. The user asked to keep multiple agents working until the broader validation goal is genuinely complete. The next defensible step is L1: prove that a meaningful subset of the catalog can be cloned at pinned commits and run native C build/test smoke commands in an external WSL workspace.

The validation gates define L1 as a native C baseline only. L1 does not prove Rust migration, unsafe budget, semantic equivalence, or performance preservation.

## Goals / Non-Goals

**Goals:**

- Produce auditable L1 evidence for at least 12 complex C/C-major projects where feasible in the current WSL environment.
- Record both passed and failed attempts with pinned commit, commands, exit codes, elapsed time, tool versions, and log paths.
- Keep upstream clones and generated build outputs outside this repository.
- Summarize the L1 state in repo-local evidence so future L2/L3 work can choose slices from proven baselines.

**Non-Goals:**

- Do not migrate all selected projects to Rust in this change.
- Do not claim C/Rust semantic equivalence for any project based on L1.
- Do not vendor upstream source trees, build directories, or long logs into this repository.
- Do not require every one of the 22 catalog projects to pass L1 before recording useful evidence.

## Decisions

- Use WSL Ubuntu as the L1 execution environment because the upstream projects mostly assume POSIX build tools and many do not build cleanly under native Windows.
- Split projects across parallel workers by domain so failures are isolated and long builds do not block all progress.
- Store raw clone/build/test logs in `C:\Users\Administrator\Documents\c-to-rust-l1-work`, and store only compact JSON evidence under `validation/evidence`.
- Treat failures as first-class evidence. A failed L1 attempt still records provenance and blocker class, but only passed projects count toward the L1 pass target.
- Prefer reduced-feature smoke builds for large projects to validate the baseline without pulling in full protocol, codec, RTOS, or server matrices.

## Risks / Trade-offs

- Large upstream builds may take a long time or exhaust machine resources. Mitigation: limit commands to `-j2` and split work into small batches.
- Moving upstream branches can drift during validation. Mitigation: record the exact post-clone commit SHA for every attempt.
- Project-specific dependencies may be missing. Mitigation: record dependency blockers and continue with other projects.
- A smoke command can be too weak. Mitigation: keep L1 claims limited to native baseline reproducibility and require L2/L3 for migration/equivalence claims.
- Logs outside the repository can be moved or deleted. Mitigation: repo evidence records enough command metadata and external paths to reproduce the attempt.

## Migration Plan

1. Prepare the WSL toolchain and external workspace.
2. Run multiple domain-specific worker batches against selected catalog projects.
3. Aggregate worker result JSON into `validation/evidence/l1-native-summary.json` and per-project evidence files.
4. Validate OpenSpec and existing Rust/FlashDB tests so this evidence change does not regress the current repository.
5. Commit and push the branch only after local validation passes.

## Open Questions

- Which failed projects, if any, should be retried with additional dependencies before the L1 pass target is considered complete?
- After L1 reaches at least 12 passed projects, which first 3-5 projects should receive L2 Rust slice migration work?

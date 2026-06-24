## Context

The current repository now has FlashDB C/Rust differential evidence and a 15-target L0 catalog. The next useful step is not to start many deep clones at once, but to expand the target set and make the L0 evidence stricter and more actionable.

本 change 仍然保持小而精：扩展候选、强化 L0、写出 L1/L2 project card。它不把远程 HEAD 探测包装成迁移完成。

## Goals / Non-Goals

**Goals:**

- Maintain at least 20 super-complex C/C-major validation targets.
- Keep target metadata concrete enough for future L1/L2 agents.
- Fail remote probe if upstream default branch differs from the catalog expectation.
- Add project cards for practical L1/L2 follow-up.

**Non-Goals:**

- This change does not clone or build all targets.
- This change does not migrate any new target to Rust.
- This change does not claim semantic equivalence for any non-FlashDB project.

## Decisions

### Decision 1: Expand catalog with harder project classes

Add projects that stress different failure modes: Valkey server behavior, zstd/libjpeg codec logic, MicroPython VM/GC, tmux terminal state, Zephyr and FreeRTOS RTOS/embedded code.

### Decision 2: Branch drift is a validation failure

When `-ProbeRemote` is explicit, the verifier should fail if the default branch differs from the catalog. This avoids silently validating stale metadata.

### Decision 3: Project cards are planning evidence, not migration evidence

The new L1/L2 project-card document lists next commands and migration slices. It is not evidence that the commands have been run.

## Risks / Trade-offs

- [Risk] More projects increase catalog maintenance. -> Mitigation: remote probe evidence records current branch and SHA.
- [Risk] Zephyr and MicroPython are multi-component projects. -> Mitigation: catalog marks them C-major and uses bounded slices.
- [Risk] Branch drift can break probes. -> Mitigation: failure is intentional and forces catalog refresh.

## Migration Plan

1. Add OpenSpec artifacts.
2. Update catalog minimum and add 7 targets.
3. Update README target count.
4. Add L1/L2 project cards.
5. Harden remote branch validation.
6. Run offline and remote L0 validators.
7. Run OpenSpec and git checks.
8. Commit, push, and inspect branch state.

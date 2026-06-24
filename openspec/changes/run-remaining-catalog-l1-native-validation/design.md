## Context

The repository has already produced L1 native C build/test smoke evidence for 36 of 40 catalog targets. The remaining targets are `ffmpeg`, `micropython`, `zephyr`, and `freertos-kernel`. They differ enough that they should run in isolated external work roots and be aggregated after completion.

L1 remains a baseline gate only. It proves a pinned upstream checkout was attempted with catalog smoke commands and records the result. It does not prove Rust migration success, C/Rust semantic equivalence, unsafe budget, or performance preservation.

## Goals / Non-Goals

**Goals:**

- Attempt L1 native C build/test smoke for all four remaining catalog targets.
- Record per-project evidence for every attempt, including failures and timeouts.
- Update the global L1 summary to show 40/40 catalog targets attempted.
- Add a remaining-catalog summary so the closure of the gap is auditable.

**Non-Goals:**

- Do not install system packages or mutate the WSL host to make builds pass.
- Do not repair failed upstream build/test smoke commands in this change.
- Do not add Rust migration slices or semantic-equivalence claims.
- Do not submit external clone directories, build artifacts, or full logs into the repository.

## Decisions

### Decision 1: Use the existing WSL runner with explicit project ids

`validation/tools/run_wave2_l1.py` already supports `--projects`, reads `validation/projects.json`, and records compact per-project results. Reusing it avoids a second command schema. The remaining change can add only the aggregation needed for a remaining-target summary.

### Decision 2: Preserve failures as first-class evidence

Projects like Zephyr and FreeRTOS may fail because the current host lacks `west`, SDKs, or a complete example harness. These failures still close the catalog state gap because they identify a concrete blocker and log path.

### Decision 3: One external work root per target family

The four targets are independent and can be run in parallel: media codec, language runtime, RTOS platform, and RTOS kernel. Workers write only to external paths, then the main thread aggregates compact evidence into the repository.

## Risks / Trade-offs

- [Risk] Zephyr or MicroPython may require submodules or SDK tools not available locally. -> Mitigation: record the failed command, exit code, and log paths without installing dependencies.
- [Risk] FFmpeg or MicroPython builds may take longer than small projects. -> Mitigation: keep runner step timeouts and accept timeout evidence if reached.
- [Risk] Existing wave2-specific aggregation should not be distorted. -> Mitigation: add a remaining-catalog summary while preserving the existing wave2 summary.
- [Risk] Project smoke commands may be too shallow or mis-specified. -> Mitigation: treat this as L1 smoke evidence only; command refinements require a later change.

## Migration Plan

1. Create and validate OpenSpec artifacts.
2. Run the four remaining targets in parallel external work roots.
3. Aggregate worker `results.json` into per-project evidence.
4. Update `validation/evidence/l1-native-summary.json` and add `remaining-l1-native-summary.json`.
5. Update README with 40/40 attempted status and reporting boundary.
6. Run catalog/OpenSpec/Rust/diff verification.
7. Commit and push the branch.

## Why

已有 catalog 覆盖 15 个复杂 C/C-major 项目，但用户要求继续“找十几个超级复杂 C 项目进行验证”。需要把候选集扩到更高复杂度，并把 L0 remote probe 从“可达”提升到“默认分支与 catalog 一致”的可审计验证。

English summary: expand the validation catalog beyond the first 15 targets and harden L0 remote probes before starting expensive L1/L2 work.

## What Changes

- Increase the catalog minimum from 12 to 20 targets.
- Add additional super-complex C/C-major targets: Valkey, zstd, libjpeg-turbo, MicroPython, tmux, Zephyr, and FreeRTOS-Kernel.
- Strengthen `validate-c-project-catalog.ps1 -ProbeRemote` so default-branch drift fails the probe.
- Add a L1/L2 project-card document that turns the catalog into concrete next validation actions.
- Preserve the boundary that L0 is not migration equivalence.

## Capabilities

### New Capabilities

- `supercomplex-c-project-expansion`: Covers expanded candidate coverage, stricter L0 remote branch validation, and L1/L2 project-card planning for the expanded set.

### Modified Capabilities

- None.

## Impact

- Updates `validation/projects.json`, `validation/README.md`, and L0 evidence files.
- Updates `scripts/validate-c-project-catalog.ps1`.
- Adds `validation/l1-l2-project-cards.md`.
- Adds OpenSpec artifacts for the new expansion change.
- Does not clone large external repositories or claim L1/L2 completion.

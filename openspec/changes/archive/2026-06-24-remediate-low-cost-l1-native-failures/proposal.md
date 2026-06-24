## Why

All 40 catalog targets now have L1 native C build/test smoke attempts, but 17 still fail. Several failures are likely repairable by bounded catalog command changes rather than host package installation, so they should be remediated and rerun before moving to deeper Rust migration claims.

## What Changes

- Identify a conservative subset of failed L1 projects that can be fixed through command/configuration changes only.
- Update `validation/projects.json` recipes for the accepted subset without installing host dependencies or broadening project scope.
- Rerun the remediated subset and generate compact JSON/Markdown evidence that distinguishes newly passed projects from still-blocked projects.
- Add or reuse aggregation tooling so remediated results update per-project L1 evidence and the global L1 native summary consistently.
- Record explicit deferrals for failures that require system packages, toolchains, network retry policy, or larger recipe design.

## Capabilities

### New Capabilities

- `l1-native-low-cost-remediation`: Covers scoped command-only remediation, rerun evidence, global L1 summary updates, and non-remediable failure boundaries.

### Modified Capabilities

- None.

## Impact

- Affected files: `validation/projects.json`, `validation/tools/**`, `validation/evidence/**`, `validation/README.md`, and OpenSpec artifacts.
- External files: creates fresh validation work roots under `C:\Users\Administrator\Documents\c-to-rust-l1-work`.
- No host package installation is performed.
- No `flashDB_rust` runtime behavior changes are expected.

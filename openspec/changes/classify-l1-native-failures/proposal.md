## Why

All 40 catalog targets now have L1 native C build/test smoke attempts, with 23 passed and 17 failed. The failed set needs structured classification before we spend time on dependency fixes, command repair, or L2 Rust slice selection.

## What Changes

- Add a reproducible failure-classification tool that reads `validation/evidence/l1-native-summary.json`, per-project L1 evidence, and external log tails.
- Generate compact JSON and Markdown reports for all failed L1 projects.
- Classify failures into actionable buckets such as missing tool, missing artifact, environment restriction, clone/network failure, timeout, upstream build failure, configure/dependency failure, and command mismatch.
- Record suggested next action per project without claiming any failed project is fixed.

## Capabilities

### New Capabilities

- `l1-native-failure-classification`: Covers deterministic classification, log-tail capture, category counts, and next-step recommendations for failed L1 native attempts.

### Modified Capabilities

- None.

## Impact

- Affected files: `validation/tools/**`, `validation/evidence/**`, `validation/README.md`, and OpenSpec artifacts.
- External files: reads log files referenced by existing evidence under `C:\Users\Administrator\Documents\c-to-rust-l1-work`.
- No C project is rebuilt in this change.
- No `flashDB_rust` runtime behavior changes are expected.

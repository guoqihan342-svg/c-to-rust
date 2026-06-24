## Why

The catalog now contains 40 complex C/C-major validation targets, but L1 native C build/test smoke evidence exists for only 36 of them. Closing the remaining four-target gap makes the catalog state explicit and prevents future work from confusing "not attempted" with "failed" or "passed".

## What Changes

- Run L1 native C build/test smoke attempts for FFmpeg, MicroPython, Zephyr, and FreeRTOS Kernel in external WSL work roots.
- Preserve each attempt as per-project evidence with pinned commit, commands, exit codes, elapsed time, tool versions, and external log paths.
- Add a compact remaining-catalog L1 summary and update the global L1 summary so all 40 catalog targets are either passed or failed, with no unattempted entries.
- Keep the reporting boundary clear: L1 is native C baseline smoke evidence only, not Rust migration, unsafe-budget, performance, or C/Rust semantic-equivalence evidence.

## Capabilities

### New Capabilities

- `remaining-catalog-l1-native-validation`: Covers L1 attempts and evidence aggregation for the four catalog targets that had no L1 evidence.

### Modified Capabilities

- None.

## Impact

- Affected files: `validation/evidence/**`, `validation/tools/**`, `validation/README.md`, and OpenSpec artifacts.
- External systems: upstream GitHub repositories cloned under `C:\Users\Administrator\Documents\c-to-rust-l1-work\remaining-l1`.
- Build and smoke commands run in WSL/Linux. Missing dependencies, build failures, test failures, or timeouts are valid L1 evidence when recorded.
- No `flashDB_rust` runtime behavior changes are expected.

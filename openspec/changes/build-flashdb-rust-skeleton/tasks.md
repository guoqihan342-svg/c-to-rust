## 1. Project Skeleton

- [x] 1.1 Create the `flashDB_rust` Cargo project with library and CLI targets.
- [x] 1.2 Add minimal dependencies and Cargo metadata while keeping the dependency set small.
- [x] 1.3 Create module files for `config`, `types`, `flash`, `format`, `kvdb`, `tsdb`, `ffi`, and CLI entrypoints.
- [x] 1.4 Export the Rust-native public API from `src/lib.rs`.

## 2. Core Types and Format Helpers

- [x] 2.1 Implement `Error`, `Result<T>`, address wrappers, status enums, and configuration types.
- [x] 2.2 Implement CRC32 helper compatible with FlashDB-style incremental CRC usage.
- [x] 2.3 Implement write-granularity alignment helpers for `FDB_WRITE_GRAN=1` and future-safe granularity values.
- [x] 2.4 Implement deterministic header/blob encoding and decoding with CRC validation.
- [x] 2.5 Implement image hashing and basic byte-size accounting for verification reports.

## 3. Flash Backends

- [x] 3.1 Implement the safe `FlashDevice` trait with read, write, erase, flush, len, and counter behavior.
- [x] 3.2 Implement deterministic `MemoryFlash` with erased-value semantics.
- [x] 3.3 Implement `FileFlash` with create/open/reopen, flush, read, write, erase, and isolated test paths.
- [x] 3.4 Add backend error behavior for out-of-bounds reads/writes and invalid erase ranges.

## 4. KVDB Seed Implementation

- [x] 4.1 Implement `KvDb` construction over a generic flash backend.
- [x] 4.2 Implement string/blob `set`, `get`, `delete`, and missing-key behavior.
- [x] 4.3 Implement deterministic iteration over live KV entries.
- [x] 4.4 Implement clear or GC-like compaction behavior for the seed format.
- [x] 4.5 Implement reopen/load behavior from the file-backed seed image.

## 5. TSDB Seed Implementation

- [x] 5.1 Implement `TsDb` construction over a generic flash backend.
- [x] 5.2 Implement append with explicit timestamp and binary payload.
- [x] 5.3 Implement query by timestamp range, including empty and reversed ranges.
- [x] 5.4 Implement count by status and status update behavior.
- [x] 5.5 Implement reopen/load behavior from the file-backed seed image.

## 6. CLI and Verification Loop

- [x] 6.1 Implement CLI commands for `smoke`, `stress`, and `inspect-image`.
- [x] 6.2 Support configurable backend, loop count, seed, scenario set, and report path.
- [x] 6.3 Implement production-like scenario loops for KVDB and TSDB main paths.
- [x] 6.4 Implement abnormal-data scenario loops for missing keys, empty keys, oversized keys, capacity errors, CRC mismatch, truncated records, and corrupted images.
- [x] 6.5 Implement reliability scenario loops for flush, reopen, repeated compaction, file-backed replay, and image hash reporting.
- [x] 6.6 Emit machine-readable verification reports with scenario counts, duration, operation counters, bytes processed, and image hashes.

## 7. Rust Tests

- [x] 7.1 Add unit tests for CRC32, alignment, encoding/decoding, corruption rejection, and status/error mapping.
- [x] 7.2 Add unit tests for `MemoryFlash` and `FileFlash`, including error paths.
- [x] 7.3 Add integration tests for KVDB set/get/delete/iterate/compact/reopen.
- [x] 7.4 Add integration tests for TSDB append/query/count/status/reopen.
- [x] 7.5 Add integration tests for CLI smoke/stress report generation with a small deterministic loop count.
- [x] 7.6 Add an unsafe scan test or script that verifies first-party non-test unsafe usage remains 0%.

## 8. Documentation and Scripts

- [x] 8.1 Add `flashDB_rust/README.md` with Chinese/English quick-start and verification commands.
- [x] 8.2 Add a local verification script for baseline checks.
- [x] 8.3 Document the exact 10000-loop long-run command and state that it is not passed until actually run.
- [x] 8.4 Record known tool fallbacks for missing native C2Rust, nextest, llvm-cov, fuzz, and geiger.

## 9. Validation

- [x] 9.1 Run `cargo fmt -- --check` in `flashDB_rust`.
- [x] 9.2 Run `cargo check` in `flashDB_rust`.
- [x] 9.3 Run `cargo test` in `flashDB_rust`.
- [x] 9.4 Run CLI smoke and a small deterministic stress loop.
- [x] 9.5 Run the unsafe scan and confirm first-party non-test unsafe usage is 0%.
- [x] 9.6 Run `openspec validate "build-flashdb-rust-skeleton" --strict`.
- [x] 9.7 Run `openspec validate --all`.
- [x] 9.8 Run `git diff --check` for the new change and `flashDB_rust`.
- [x] 9.9 Summarize remaining gap to real 10000-loop production/abnormal/performance/reliability/full-branch verification if the full long run has not yet completed.

## 1. OpenSpec And Gates

- [x] 1.1 Add OpenSpec requirements for L2 unsafe ledger, deterministic corpus, and negative diff evidence.
- [x] 1.2 Update `validation/gates.md` so L2 pass criteria require unsafe ledger and L2 negative diff evidence.

## 2. Deterministic C Oracle Corpus

- [x] 2.1 Expand `zlib-adler32` C oracle fixture generation with fixed-seed deterministic byte buffers.
- [x] 2.2 Regenerate `zlib-adler32-c-oracle.json`, `zlib-adler32-oracle.json`, and `c-oracle-summary.json`.

## 3. Rust Evidence Generation

- [x] 3.1 Update `emit_reports.rs` to produce `unsafe-ledger.json`.
- [x] 3.2 Update `emit_reports.rs` to produce `zlib-adler32-negative-diff.json`.
- [x] 3.3 Update `l2-l3-summary.json` to reference unsafe ledger and negative diff status.

## 4. Verification

- [x] 4.1 Run L2 formatting, tests, and report generation.
- [x] 4.2 Run OpenSpec validation and whitespace validation.
- [x] 4.3 Run FlashDB Rust regression formatting and tests.

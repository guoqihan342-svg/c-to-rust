## 1. Fixture and Rust Diff

- [x] 1.1 Add `fixtures/c-rust-smoke.json` with deterministic comparable KVDB/TSDB operations.
- [x] 1.2 Update Rust `diff` to compare report steps and selected fields instead of whole-file text.
- [x] 1.3 Implement accepted-difference handling for fields such as `image_hash`, metadata, and messages.
- [x] 1.4 Add tests for metadata-only differences passing and behavior value differences failing.

## 2. C Oracle Fixture Replay

- [x] 2.1 Pass `--fixture` from `generate_c_oracle.sh` into the C executable.
- [x] 2.2 Make the C executable parse the fixture operation subset and output matching step ids and operation names.
- [x] 2.3 Map C/FDB success and error results to stable Rust-compatible codes.
- [x] 2.4 Produce comparable KVDB and TSDB behavior fields for the fixture.

## 3. CI Integration

- [x] 3.1 Update `verify-ci.sh` to run Rust replay for `fixtures/c-rust-smoke.json`.
- [x] 3.2 Update `verify-ci.sh` to diff Rust replay report against the generated C oracle report.
- [x] 3.3 Ensure C/Rust diff failure fails CI and writes evidence.

## 4. Validation

- [x] 4.1 Run Rust fmt/check/test.
- [x] 4.2 Run WSL C oracle producer with `fixtures/c-rust-smoke.json`.
- [x] 4.3 Run Rust-vs-C diff locally through WSL-generated C report.
- [x] 4.4 Run replay/diff smoke, CLI smoke, stress sample, and unsafe scan.
- [x] 4.5 Run release 10000-loop stress.
- [x] 4.6 Run `openspec validate "add-schema-aware-c-rust-diff" --strict`.
- [x] 4.7 Run `openspec validate --all`.
- [x] 4.8 Run `git diff --check`.
- [ ] 4.9 Push branch and inspect GitHub Actions C/Rust diff result.

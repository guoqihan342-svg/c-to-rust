## 1. CI Producer Enforcement

- [x] 1.1 Configure the GitHub Actions verification step with `FLASHDB_C_ORACLE_PRODUCER=./oracle/generate_c_oracle.sh`.
- [x] 1.2 Update `verify-ci.sh` so configured C oracle producer failures fail the job.
- [x] 1.3 Preserve explicit skip evidence only for missing C compiler or intentionally unconfigured local usage.

## 2. Evidence and Documentation

- [x] 2.1 Ensure C oracle success evidence records `C_ORACLE_PRODUCER_PASSED` and the oracle report hash.
- [x] 2.2 Ensure C oracle generation evidence does not claim full C/Rust semantic equivalence.
- [x] 2.3 Update README or script comments if command behavior changed.

## 3. Validation

- [x] 3.1 Run `cargo fmt -- --check`.
- [x] 3.2 Run `cargo check`.
- [x] 3.3 Run `cargo test`.
- [x] 3.4 Run replay/diff smoke, CLI smoke, stress sample, and unsafe scan.
- [x] 3.5 Run release 10000-loop stress or preserve and verify current recorded evidence if implementation did not affect stress behavior.
- [x] 3.6 Run `openspec validate "require-ci-c-oracle-generation" --strict`.
- [x] 3.7 Run `openspec validate --all`.
- [x] 3.8 Run `git diff --check`.
- [ ] 3.9 Push branch and inspect GitHub Actions result for real C oracle producer execution.

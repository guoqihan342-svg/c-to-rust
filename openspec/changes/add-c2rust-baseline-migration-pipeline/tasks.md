## 1. OpenSpec And Evidence Contract

- [x] 1.1 Validate the new OpenSpec proposal, design, and specs under `add-c2rust-baseline-migration-pipeline`.
- [x] 1.2 Add route-decision, C2Rust baseline manifest, and validation-profile artifacts to the auto-translation evidence contract.
- [x] 1.3 Update validation documentation so Agent workers know C2Rust is optional baseline context, not correctness evidence.

## 2. Auto Migration Evidence Implementation

- [x] 2.1 Add tests that require `auto_migrate.py` to emit `l3-<slice>-c2rust-baseline-manifest.json`.
- [x] 2.2 Implement C2Rust baseline probing with explicit generated, skipped, or blocked status and cache inputs.
- [x] 2.3 Add tests that require `auto_migrate.py` to emit `l3-<slice>-route-decision.json`.
- [x] 2.4 Implement conservative L0-L4 route-decision evidence from current type, CFG, pointer, translator, and blocked facts.
- [x] 2.5 Add tests that require `auto_migrate.py` to emit `l3-<slice>-validation-profile.json`.
- [x] 2.6 Implement validation-profile evidence with route level, run goal, required gates, optional gates, skipped gates, and result.
- [x] 2.7 Add negative tests that a generated C2Rust baseline, skipped required gate, or Agent candidate cannot mark a slice accepted without the selected validation profile passing.
- [x] 2.8 Bind the three new artifacts into final L3 auto-translation manifest and cache metadata.
- [x] 2.9 Update legacy wording so any C2Rust oracle reference is interpreted as baseline/cross-check only, not a replacement for original C oracle/diff gates.

## 3. Real FlashDB Slice Verification

- [x] 3.1 Re-run the real-source `fdb_calc_crc32` extraction/auto-migration path and confirm blocked evidence remains fail-closed.
- [x] 3.2 Run focused Python unit tests for extractor, auto migration, and evidence validation.
- [x] 3.3 Run `openspec validate --all --strict` and `git diff --check`.
- [x] 3.4 Summarize current accepted, blocked, skipped, and next-step evidence without claiming semantic acceptance for blocked slices.

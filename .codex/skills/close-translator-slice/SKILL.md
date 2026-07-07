---
name: close-translator-slice
description: Use when finalizing or reviewing a c2r-translator slice after translator source changes, especially to sync bounded tests, translator coverage matrix entries, bilingual roadmap/docs, and candidate-vs-semantic evidence boundaries before handoff, commit, or push.
---

# Close Translator Slice

## Scope

Use this only after a bounded translator change exists. Use `translation-minimal-slice` for initial slice selection and implementation.

This is repo-local developer guidance. Do not add API keys, provider credentials, competition host settings, judge configs, or competition archive inputs to this skill.

## Closure Workflow

1. Inspect the diff with `git diff --name-only` and identify the exact construct or refusal behavior that changed.
2. Confirm a focused bounded translator test covers the new behavior, and a negative test covers the nearest fail-closed boundary when the change relaxes an emitter/refusal rule.
3. Update `validation/translator-coverage-matrix.json` only for the changed capability or refusal. Keep unit-test evidence separate from C/Rust semantic acceptance evidence.
4. Update `docs/c2rust-migration-agent/future-vision-and-mvp.md` and `.en.md` only when user-facing capability, boundary, or next-step wording changed. Keep the Chinese file canonical and the English mirror synchronized.
5. Preserve claim boundaries. Generated Rust, typed-IR emission, rustc compile checks, and green unit tests are `candidate_context_only` unless C oracle, Rust replay, diff, negative diff, unsafe ledger, and validation profile prove the declared semantic slice.
6. Leave the next blocked slice explicit, usually the closest still-refused construct or evidence gate.

## Verification

Choose the smallest useful command set:

```bash
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features=clang-lowering-report --test bounded_translation <focused-test-filter>
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features=clang-lowering-report --test bounded_translation --quiet
python -B validation/tools/translator_coverage_matrix.py --matrix validation/translator-coverage-matrix.json
python -B -m unittest validation.tools.test_doc_mirror_contract
python -B -m unittest validation.tools.test_validate_test_translation_coverage
git diff --check
```

Broaden to auto-translation validators only when route/profile/final-verification evidence changed.

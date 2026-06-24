## Why

The current gates prove strong C/Rust replay and diff evidence, but they do not require a dedicated code-test translation manifest that maps C tests, fixtures, oracle expectations, and Rust tests together. Future migrations need this mapping so code translation and test translation advance together, and so an agent cannot claim L2/L3 success from code-only work.

中文：当前门禁已经有较强的 C/Rust replay 和 diff 证据，但还没有专门的 code-test translation manifest，把 C 测试、fixture、oracle expectation 与 Rust tests 绑定起来。后续迁移需要这个映射，避免只翻代码、不同步迁移测试。

## What Changes

- Add a reusable `validation/test-translation-template/` with README, checklist, schema, and FlashDB example.
- Require L2/L3 slices to record C test or fixture sources, Rust test files and test names, coverage of main paths and error paths, negative cases, and evidence links.
- Update L3 template manifests so future L3 evidence references `evidence.test_translation`.
- Keep runtime unchanged: no new dependencies, no test generator, no CI workflow changes in this slice.

## Capabilities

### New Capabilities

- `code-test-translation-gate`: Defines the evidence needed to prove code translation and test translation are synchronized for bounded C-to-Rust slices.

### Modified Capabilities

- `l3-validation-template`: Adds test-translation evidence references to the reusable L3 evidence package.

## Impact

- Affected docs/templates: `validation/test-translation-template/`, `validation/l3-template/`, `validation/gates.md`, `validation/README.md`.
- Affected OpenSpec artifacts: new capability spec plus an L3 template delta.
- No Rust runtime behavior changes.
- No new dependencies.
- Historical evidence remains historical; future L2/L3 slices must provide test translation evidence or explicitly mark why it is not applicable.

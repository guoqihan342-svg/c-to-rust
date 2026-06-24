## Why

L3 evidence already binds FlashDB slices to a pinned source commit and fixture, but macro/config/profile facts are still spread across version manifests, cache metadata, and C oracle files. Future pointer-heavy or macro-heavy C slices need a small, explicit config-profile gate so cached C/Rust equivalence evidence cannot float across changed `#define`, feature, include, or toolchain inputs.

中文：现有 L3 证据已经绑定 FlashDB source commit 和 fixture，但宏、配置、feature、include/profile 信息仍分散在 version manifest、cache metadata 和 C oracle 文件里。后续进入指针更重、宏更多的 C 项目时，需要一个轻量 config-profile 门禁，避免缓存证据在 `#define`、feature、include 或工具链输入变化后继续被误用。

## What Changes

- Add a reusable L3 config-profile schema and example under `validation/l3-template/`.
- Extend the L3 evidence manifest schema so future per-slice manifests must reference a config profile and expose normalized config facts.
- Update the L3 checklist, README, and gates to require profile binding before claiming semantic equivalence.
- Keep this change intentionally lightweight: no macro solver, no symbolic activation-condition engine, and no runtime code changes.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `l3-validation-template`: Adds explicit config-profile evidence requirements to the existing reusable L3 template.

## Impact

- Affected docs/templates: `validation/l3-template/`, `validation/gates.md`, `validation/README.md`.
- Affected OpenSpec artifacts: new change-local capability spec.
- No Rust runtime behavior changes.
- No new dependencies.
- Historical FlashDB evidence remains valid as historical evidence; future L3 slices must provide explicit or equivalent config-profile binding.

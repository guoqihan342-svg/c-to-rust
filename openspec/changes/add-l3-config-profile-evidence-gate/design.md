## Context

The current FlashDB L3 chain already records useful profile facts:

- `validation/evidence/flashdb/version-governance-manifest.json` records toolchain versions, source commit, package versions, feature matrix, and cache-key inputs.
- `validation/evidence/flashdb/*-cache-metadata.json` records source/repo commits, fixture hashes, command arguments, `feature_env`, and oracle config hashes.
- `flashDB_rust/oracle/fdb_cfg.h` is the concrete C config header used by the C oracle.

The gap is not missing data; it is missing a normalized contract that tells future agents which profile fields must be present before reusing or reporting L3 equivalence evidence.

中文：当前缺口不是完全没有数据，而是缺少一个规范化契约，告诉后续 Agent 哪些 profile 字段必须存在，才能复用或报告 L3 等价证据。

## Goals / Non-Goals

**Goals:**

- Define a small config-profile evidence shape for L3 slices.
- Bind profile identity to C config header hash, `#define` values, feature matrix, compile/include profile, Rust feature/backend profile, toolchain versions, fixture hash, and cache invalidation keys.
- Extend the reusable L3 template so future slices can validate profile presence without reading every historical FlashDB evidence file.
- Preserve historical evidence and avoid forcing old slices to be rewritten.

**Non-Goals:**

- Do not implement Hayroll-style symbolic activation-condition inference.
- Do not parse every upstream macro expansion or C preprocessor branch.
- Do not change Rust runtime behavior or FlashDB migration logic.
- Do not add new dependencies or a new validator binary in this change.

## Decisions

- Use a profile schema plus example, not executable analysis.
  - Rationale: the current need is traceability and cache invalidation discipline. A schema is cheap, deterministic, and agent-readable.
  - Alternative considered: add a full macro-diff analyzer. Deferred because it is larger than the present evidence gap and would violate the small-and-focused project constraint.

- Treat config profile as part of L3 identity.
  - Rationale: C oracle output, Rust replay, schema diff, unsafe evidence, and performance smoke are only reusable when the source commit, fixture, config header, feature matrix, command args, and toolchain profile still match.
  - Alternative considered: keep config facts only inside cache metadata. Rejected because cache metadata is inconsistent across historical slices.

- Keep legacy slices grandfathered.
  - Rationale: existing FlashDB L3 evidence predates this gate and should remain auditable history. The new gate applies to future L3 claims and template consumers.
  - Alternative considered: rewrite all existing FlashDB evidence. Rejected because it would create large churn without improving current runtime correctness.

## Risks / Trade-offs

- [Risk] Agents may treat the schema as proof of macro semantic coverage. -> Mitigation: README and gates state this profile is a binding and invalidation contract, not a macro solver.
- [Risk] Historical evidence has heterogeneous field names. -> Mitigation: template accepts equivalent binding while making new future fields canonical.
- [Risk] The profile becomes too broad and hard to fill. -> Mitigation: required fields are limited to profile identity, hashes, defines/features, compile profile, and invalidation keys.
- [Risk] Runtime performance optimization work gets mixed into the evidence gate. -> Mitigation: this change only records profile inputs; async, multithreading, and cache-runtime semantics stay non-goals unless separately proven.

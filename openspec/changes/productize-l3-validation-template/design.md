## Context

FlashDB already has multiple L3 slices with strong evidence, including `kvdb-lifecycle`, `kvdb-compact-overwrite`, `tsdb-user2-status`, and other TSDB/KVDB boundary slices. The strongest summaries record the same pattern: slice contract, context pack, C oracle generated from the pinned FlashDB source, Rust replay report, schema-aware diff, negative diff, rust check, unsafe scan/ledger, performance smoke, known gaps, accepted differences, and final verification.

当前问题不是缺少单个 FlashDB L3 证据，而是缺少一个可复用模板来告诉后续 Agent 哪些文件必须存在、哪些状态才算通过、哪些结论不能被扩大。该模板应服务未来更复杂 C 项目的 L3 切片，而不是只服务 FlashDB。

## Goals / Non-Goals

**Goals:**

- Create `validation/l3-template/` with a bilingual README, checklist, and machine-readable evidence manifest.
- Define required and optional L3 evidence artifacts with expected status semantics.
- Bind L3 claims to pinned source commit, fixture hash, version/config manifest, and named slice boundary.
- Require negative diff evidence and explicit known gaps before any semantic-equivalence claim.
- Keep the template dependency-free and easy for other agents to consume.

**Non-Goals:**

- Do not modify existing FlashDB L3 evidence files.
- Do not implement a generic L3 validator binary in this change.
- Do not introduce new Rust, Python, or Node dependencies.
- Do not archive existing L3 changes.
- Do not claim full FlashDB migration or byte-for-byte image equivalence.

## Decisions

- Use `validation/l3-template/` as docs plus JSON manifest, not executable code.
  - Rationale: the immediate gap is repeatable evidence shape. A static manifest is cheap, reviewable, and usable by opencode or other agents.
  - Alternative considered: write a full validator. Deferred because evidence schemas vary between older and newer L3 slices, and a hard validator should follow after the template stabilizes.

- Treat negative diff as required.
  - Rationale: positive schema diff alone does not prove the diff gate catches behavior regressions. Existing high-quality FlashDB slices already include negative diff evidence.
  - Alternative considered: make negative diff optional. Rejected because it is one of the highest-value protections against false equivalence claims.

- Separate required and optional evidence.
  - Rationale: not every slice has agent roles, cache metadata, or final markdown summaries, but every L3 claim needs C oracle/Rust replay/diff/negative diff/safety/version boundary.
  - Alternative considered: require every historical artifact for all future slices. Rejected to avoid blocking small valid slices on nonessential metadata.

## Risks / Trade-offs

- [Risk] A template without an executable checker may be ignored. -> Mitigation: include a machine-readable manifest and verification checklist so a future validator can be added without reworking the format.
- [Risk] Historical FlashDB slices use slightly different summary field names. -> Mitigation: the template defines canonical future keys while listing existing examples as references, not as strict legacy schemas.
- [Risk] Agents may use performance smoke as proof of equivalence. -> Mitigation: template explicitly marks performance as secondary-only evidence.
- [Risk] Windows local C oracle skips may be misreported as L3 passes. -> Mitigation: template requires `C_ORACLE_GENERATED` or an explicit non-pass skip marker and replacement evidence.


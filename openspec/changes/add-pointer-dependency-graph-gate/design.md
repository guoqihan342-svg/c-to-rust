## Context

Existing evidence already captures useful boundaries:

- Context packs record direct modules, public APIs, tests, cache keys, unsafe status, and rollback ids.
- Impact sets record affected Rust files, semantic boundaries, and unsafe policy.
- Unsafe ledgers record first-party Rust unsafe usage after migration.
- Config profiles bind evidence to macro/config/toolchain inputs.

The missing layer is a pre-translation pointer dependency graph that describes how C pointer-like values relate to each other before the Rust mapping is chosen. This is especially important for future slices in projects such as libuv, nginx, OpenSSL, SQLite, Redis, or kernel-adjacent targets where aliases can propagate through structs, callbacks, buffers, and external state.

中文：现有证据能说明模块边界和 Rust unsafe 结果，但还缺一个“翻译前”的 C 指针依赖图，用于描述指针值、别名、所有权、生命周期、外部状态和 Rust 映射策略之间的关系。

## Goals / Non-Goals

**Goals:**

- Add a reusable pointer graph evidence template that other agents can fill before pointer-heavy migration work.
- Make pointer graph evidence conditional: required for pointer-bearing slices and explicitly `not_applicable` for pure value slices.
- Keep fields small enough for token discipline but complete enough to preserve cross-file dependency context.
- Bind pointer graph evidence to source commit, slice id, source files, config profile, and cache invalidation keys.

**Non-Goals:**

- Do not implement a whole-program alias analyzer.
- Do not guarantee safe Rust translation from graph presence alone.
- Do not rewrite historical FlashDB evidence.
- Do not add runtime dependencies, CLI commands, or Rust code in this change.
- Do not relax the unsafe budget; new unsafe still requires ledger evidence and tests.

## Decisions

- Use a template plus schema rather than an analyzer.
  - Rationale: the project needs a reliable evidence shape first. A schema gives future agents a deterministic contract without adding heavy tooling.
  - Alternative considered: implement pointer analysis now. Deferred because accurate C pointer analysis is larger than the current “small and focused” optimization.

- Make the gate conditional and explicit.
  - Rationale: pure value slices such as checksums should not carry fake pointer graphs, but pointer-heavy slices must not skip the graph silently.
  - Alternative considered: require graph evidence for every slice with no bypass. Rejected because it adds noise to pure functions and weakens signal.

- Separate pointer graph from unsafe ledger.
  - Rationale: pointer graph is pre-translation C context; unsafe ledger is post-translation Rust risk accounting. Both are useful but answer different questions.
  - Alternative considered: put pointer facts into unsafe ledger. Rejected because safe Rust can still depend on pointer-derived ownership assumptions.

## Risks / Trade-offs

- [Risk] Agents may treat graph presence as proof of alias safety. -> Mitigation: README and gates state the graph is dependency evidence, not a proof.
- [Risk] Manual graphs may be incomplete. -> Mitigation: schema requires source boundary, nodes, edges, uncovered assumptions, and invalidation keys.
- [Risk] Historical evidence lacks this artifact. -> Mitigation: apply the rule to future pointer-bearing slices and preserve historical evidence unchanged.
- [Risk] The graph becomes too verbose. -> Mitigation: fields focus on nodes, edges, ownership/lifetime, external state, Rust mapping, tests, and cache keys only.

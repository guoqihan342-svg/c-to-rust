## Context

当前仓库已经完成 `flashDB_rust` 骨架、FlashDB L3 oracle/replay/diff、L2/L3 evidence 模板、unsafe ledger、pointer graph、code-test translation gate、compile self-healing 与 `validation/tools/auto_migrate.py` 的受限自动迁移闭环。最新真实源码实验已经能从 FlashDB 提取 `fdb_calc_crc32` 并生成完整 evidence-bound blocked run，但翻译被常见 C 构造阻塞，说明当前手写扫描前端不足以支撑真实项目规模化迁移。

本 change 采用 `C:\Users\Administrator\Downloads\c2r-migration-pipeline-design.md` 的主线，并按项目要求修正：测试轮数不写死；不区分廉价/强模型；`unsafe` 预算为小于 10%；C2Rust/libclang/tree-sitter/Agent 都是候选或事实来源，最终接受权只属于验证门禁。`F:\agent\c2rust-master` 是本机参考 C2Rust 源树，不是目标仓库；实现必须能在缺少可执行 C2Rust/libclang 工具时产出 skipped/blocked evidence，而不是伪造成功。

## Goals / Non-Goals

**Goals:**

- 建立 C2Rust baseline migration pipeline：真实 C 源码绑定、build profile、tree-sitter 句法索引、libclang 语义事实、可选 C2Rust unsafe baseline、L0-L4 route decision、Agent candidate、validation profile 与 L3 evidence manifest。
- 将当前手写翻译器降级为 Tier 1 deterministic fast path，并让它消费已解析类型/语义事实，而不是扩大字符串扫描规则。
- 让 `auto_migrate.py` 先能为一个真实 FlashDB 函数输出 route decision、baseline manifest、validation profile、Agent candidate manifest 与 blocked/accepted evidence。
- 保持 fail-closed：未通过 C oracle/Rust replay/diff/fuzz-property/unsafe ledger/OpenSpec evidence 的候选不能被接受。
- 支持单点渐进迁移：每个 accepted slice 必须不破坏 `flashDB_rust` 构建、测试和 C/Rust 调用边界。

**Non-Goals:**

- 不声明通用 C99/C11 全自动翻译。
- 不把 C2Rust 输出、Agent 输出、Rust 编译通过或手写翻译器输出当作正确性证据。
- 不要求所有 slice 必须使用 Kani；Kani 是高风险或 release profile 的可上调门禁。
- 不把每个函数都创建成独立 OpenSpec change；OpenSpec change 管控能力或批次，slice-level evidence manifest 管控单个函数。
- 不在本 change 中完成完整 FFI 替换、全 FlashDB 迁移或第二个复杂项目迁移。

## Decisions

### Decision 1: C2Rust is an optional unsafe baseline, not the acceptance source

C2Rust integration will record command availability, input compile profile, generated unsafe Rust path, stdout/stderr hashes, baseline source hash, and unsupported reasons. If executable C2Rust is unavailable, the run records `C2RUST_SKIPPED_TOOL_UNAVAILABLE` and continues with deterministic analysis where possible.

Rationale: C2Rust is valuable as a mature clang-backed translator and reference baseline, but accepting a migration still requires Rust candidate code to pass project gates. Treating C2Rust output as proof would violate the existing oracle/evidence contract.

Alternative considered: make C2Rust the mandatory first step. Rejected because this Windows host currently uses `F:\agent\c2rust-master` as a reference tree, not a proven installed command, and because optional evidence keeps non-C2Rust gates testable.

### Decision 2: libclang/compile profile owns semantic facts; tree-sitter owns syntax indexing

The frontend stack is split by trust level:

- tree-sitter or bounded source scanning may locate function spans and cheap syntax features.
- compile profile, compile commands, clang/libclang, C2Rust baseline, or explicit unsupported records must provide typedef, macro expansion, ABI, integer width, struct layout, implicit cast, and declaration disambiguation facts.
- missing semantic facts upgrade route difficulty or block acceptance.

Rationale: tree-sitter is fast and useful, but it is not a C semantic engine. The current project already learned that scanning source text cannot safely handle integer promotion, pointer roles, macro effects, or typedef/layout semantics.

### Decision 3: L0-L4 route decisions become first-class evidence

Every run emits `l3-<slice>-route-decision.json` with:

- `level`: `L0`, `L1`, `L2`, `L3`, or `L4`
- `translator`: deterministic rule, Agent candidate, or refuse
- `rationale`: top features that drove the decision
- `verification_profile`: required gates for this route and goal
- `misroute`: later gate failure that forced an upgrade, if any

Rationale: routing controls cost and context size, but not correctness. Recording route evidence makes misclassification auditable and prevents a cheap path from silently becoming a success path.

### Decision 4: Agent integration is provider-agnostic

Codex, OpenCode, or another Agent may generate or repair candidates from compact context bundles. The project records provider/model labels only when available. It does not require a DeepSeek-style cheap/strong split, and it does not encode a fixed repair round count as a project requirement.

Rationale: the user-facing tool model is a single Agent interface. Accuracy and verification matter more than model pricing categories. Retry budgets remain policy inputs to prevent infinite loops.

### Decision 5: C UB and Rust UB use different gates

C-side UB suspicion is handled through clang diagnostics, sanitizer-backed oracle builds where available, static flags, and explicit unsupported evidence. Rust-side UB and unsafe assumptions are checked through MIRI where applicable plus unsafe ledger review. Kani is a policy-upgraded gate for bounded high-risk slices, not a universal pointer requirement.

Rationale: MIRI does not execute C source. Keeping C and Rust UB evidence separate prevents false claims and makes tool availability explicit.

### Decision 6: OpenSpec controls capabilities; evidence manifests control slices

This change defines capability-level requirements. Individual function migrations are recorded in slice specs, route decisions, manifests, logs, and evidence directories. A batch or capability may have one OpenSpec change; each function does not need its own change unless its behavior changes the project contract.

Rationale: OpenSpec should stay readable and reviewable. Slice-level evidence is already machine-readable and better suited to high-volume migration records.

## Risks / Trade-offs

- C2Rust/libclang unavailable on the host -> record skipped/blocked evidence and keep deterministic gates runnable; use WSL/Linux/CI later for accepted semantic runs.
- Route schema expands evidence volume -> keep route decision compact, link larger context artifacts by hash/path.
- Agent candidates may over-edit public APIs -> enforce fixed slice boundary, forbidden changes, unsafe budget, and verification profile before acceptance.
- Kani/MIRI/fuzz tooling can be expensive or unavailable -> make them profile-driven gates and record skipped reasons; do not claim accepted equivalence for profiles whose required gates are skipped.
- Existing dirty evidence state can obscure new results -> new files use slice-specific paths and manifest hashes; validation includes evidence cleanliness and git diff review.

## Migration Plan

1. Add OpenSpec requirements for the C2Rust baseline pipeline and bounded-auto evidence extensions.
2. Add schema/test coverage for route decision, baseline manifest, and validation profile artifacts.
3. Extend `extract_source_slice.py` and `auto_migrate.py` to emit route decision and frontend/baseline availability evidence for the existing real FlashDB slice.
4. Add a small C2Rust adapter that can probe `F:\agent\c2rust-master` and/or installed commands, record availability, and produce skipped evidence when not executable.
5. Run the existing real-source `fdb_calc_crc32` flow through the updated evidence path; blocked status remains acceptable unless all required semantic gates pass.
6. Validate with Python unit tests, `cargo test` where relevant, `openspec validate --all --strict`, and `git diff --check`.

## Open Questions

- Which executable path should be preferred when C2Rust is installed: repo-local built binary, PATH binary, or WSL command wrapper?
- Should libclang facts be gathered through Python bindings, clang JSON AST dumps, or a Rust helper crate in the first implementation?
- What is the first accepted semantic target after `fdb_calc_crc32` remains a blocked evidence case: a scalar-only FlashDB helper or a generated C2Rust baseline smoke slice?

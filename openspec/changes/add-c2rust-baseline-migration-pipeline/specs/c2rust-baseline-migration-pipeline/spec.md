## ADDED Requirements

### Requirement: Frontend Stack Separates Syntax Baseline And Semantic Facts
The system SHALL build migration context from a layered frontend stack where syntax indexing, semantic facts, and optional unsafe baseline evidence are recorded separately.

系统必须用分层前端构建迁移上下文，并分别记录句法索引、语义事实和可选 unsafe baseline 证据。

#### Scenario: Syntax frontend records slice location only
- **WHEN** tree-sitter or bounded source scanning locates a C function or syntax feature
- **THEN** the evidence records source path, source span, syntax features, parser name, parser version, and confidence
- **AND** the syntax frontend output MUST NOT be used as proof of typedef, macro expansion, ABI, struct layout, integer promotion, implicit cast, or alias facts

#### Scenario: Semantic facts require typed frontend evidence
- **WHEN** a route decision or deterministic rule depends on C type, layout, integer width, macro-expanded expression, implicit cast, enum value, pointer mutability, or function signature facts
- **THEN** accepted semantic facts MUST come from compile profile, compile commands, `CLANG_PATH`-driven clang AST dump JSON, original C oracle evidence, or explicit unsupported semantic records; `LIBCLANG_PATH` is ignored diagnostic metadata unless a future explicit libclang adapter is enabled
- **AND** C2Rust baseline evidence MAY provide candidate context or cross-check hints
- **AND** C2Rust baseline evidence MUST NOT by itself satisfy a typed semantic fact required for acceptance
- **AND** missing semantic facts MUST upgrade the route level or block acceptance

#### Scenario: C2Rust baseline is optional evidence
- **WHEN** C2Rust is available for a slice
- **THEN** the run records C2Rust command inputs, output paths, stdout/stderr hashes, generated baseline hash, tool version, source commit, and whether the baseline was supplied to Agent context
- **AND** the C2Rust baseline MUST be treated as candidate context, not correctness evidence

#### Scenario: Legacy C2Rust oracle wording is narrowed
- **WHEN** an older design note, report, or spec refers to a C2Rust oracle or C2Rust-backed correctness proof
- **THEN** this pipeline interprets that reference as baseline or cross-check evidence only
- **AND** it MUST NOT replace the original C oracle, Rust replay, schema-aware diff, negative diff, unsafe ledger, or selected validation profile gates

#### Scenario: C2Rust unavailable does not fake success
- **WHEN** C2Rust is unavailable, not executable, or cannot consume the slice build profile
- **THEN** the run records `C2RUST_SKIPPED` or `C2RUST_BLOCKED` with command discovery diagnostics and required environment notes
- **AND** non-C2Rust gates MAY continue
- **AND** final semantic acceptance MUST NOT claim C2Rust-backed evidence for that run

### Requirement: Route Decisions Are Evidence-Bound
The system SHALL emit an auditable route decision for each automatic migration unit before translation or Agent candidate generation.

系统必须在翻译或 Agent 候选生成前，为每个自动迁移单元输出可审计 route decision。

#### Scenario: Route decision records level and rationale
- **WHEN** a slice is prepared for migration
- **THEN** the run writes `l3-<slice>-route-decision.json` with route level, translator path, rationale features, required validation profile, source artifact hashes, and policy inputs

#### Scenario: L4 route refuses unsupported semantics
- **WHEN** the frontend facts show inline assembly, nonlocal control flow, unsupported platform intrinsics, unproven invisible global state, or suspected C undefined behavior that cannot be cleared by accepted C-side evidence
- **THEN** the route decision level is `L4`
- **AND** the translator path is `refuse`
- **AND** the run writes blocked evidence instead of Rust success evidence

#### Scenario: Misroute upgrades without accepting failure
- **WHEN** a Tier 1 deterministic route produces a candidate that fails a required gate
- **THEN** the run records a misroute event with failed gate, failing input or diagnostic, original route rationale, and upgraded route level
- **AND** the failed candidate MUST NOT be accepted

### Requirement: Validation Profile Follows Route And Goal
The system SHALL bind accepted migration claims to a validation profile derived from route level and run goal.

系统必须把 accepted 迁移声明绑定到由 route level 和运行目标决定的 validation profile。

#### Scenario: Validation profile is recorded
- **WHEN** a migration run reaches verification
- **THEN** the evidence records the selected profile name, route level, run goal, required gates, optional gates, skipped gates, skip reasons, and final pass or block status

#### Scenario: Test loop counts are policy inputs
- **WHEN** a verification profile includes stress or regression loops
- **THEN** the loop count comes from the run policy or release profile
- **AND** no fixed 10-round or 10000-round loop count is required by the project contract

#### Scenario: C and Rust UB evidence are separated
- **WHEN** undefined-behavior evidence is evaluated
- **THEN** C-side UB suspicion is recorded from clang diagnostics, sanitizer-backed oracle builds, static analysis, or explicit unsupported records
- **AND** Rust-side UB or unsafe checks are recorded from MIRI, unsafe ledger review, or other Rust verification tools
- **AND** MIRI output alone MUST NOT be presented as C-source UB proof

### Requirement: Agent Candidate Generation Is Provider-Agnostic
The system SHALL allow Codex, OpenCode, or another Agent to generate or repair candidates from bounded context without making any Agent output authoritative.

系统必须允许 Codex、OpenCode 或其他 Agent 基于受限上下文生成或修复候选，但任何 Agent 输出都不得成为权威正确性证据。

#### Scenario: Agent receives compact context bundle
- **WHEN** Agent candidate generation is requested
- **THEN** the request includes only the slice spec, route decision, relevant type facts, pointer graph excerpts, direct caller/callee facts, optional C2Rust baseline excerpts, current candidate hash, and structured repair hints needed for the task

#### Scenario: Agent candidate is accepted only by gates
- **WHEN** an Agent returns Rust code, a PatchPlan, or a repair candidate
- **THEN** the run records provider label when available, prompt or context hash, output hash, applied status, and verification gates that accepted or rejected the candidate
- **AND** the candidate is accepted only if the required validation profile passes

#### Scenario: Repair budget is configurable
- **WHEN** compile self-healing or semantic repair repeats
- **THEN** the maximum retry count is taken from run policy
- **AND** exceeding the configured budget marks the slice blocked with accumulated repair hints and evidence

### Requirement: Incremental Migration Preserves Module Boundaries
The system SHALL migrate one bounded unit at a time while preserving existing C/Rust call boundaries until replacement is verified.

系统必须一次迁移一个受限单元，并在替换被验证前保持现有 C/Rust 调用边界。

#### Scenario: FFI boundary is preserved before replacement
- **WHEN** a slice is migrated while other C modules still call or are called by it
- **THEN** the migration evidence records preserved FFI signatures, imported C callees, exported Rust symbols, and compatibility tests
- **AND** public boundary changes outside the approved impact set MUST block acceptance

#### Scenario: Unsafe budget applies to incremental FFI
- **WHEN** incremental migration requires `extern "C"`, raw pointer, or shim-level unsafe
- **THEN** every unsafe region is recorded in the unsafe ledger with category, reason, evidence reference, and tests or audits
- **AND** final verification fails if first-party non-test unsafe ratio is 10% or higher

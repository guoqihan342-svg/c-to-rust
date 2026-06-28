# bounded-auto-translation-pipeline Specification

## Purpose
This spec defines the fail-closed automatic translation pipeline for real C source slices. It requires generated slice-spec provenance, context/type/CFG/pointer evidence, candidate-only Rust draft generation, C oracle/Rust replay/diff/negative/unsafe/version gates, and cache invalidation before any named-slice L3 semantic claim is accepted.
## Requirements
### Requirement: Machine-Generated Slice Spec And Build Profile Input
The system SHALL start every automatic translation run from a machine-generated slice spec whose C target has passed L1 native validation and whose build profile is sufficient to reproduce preprocessing, type, ABI, and fixture boundaries.

The slice spec SHALL be an intermediate contract and evidence anchor generated from real C source, not the primary human-authored translation input.

系统必须从机器生成的 slice spec 开始自动翻译；该 slice 对应的 C target 必须已经通过 L1 native validation，并且 build profile 必须足以复现预处理、类型、ABI 与 fixture 边界。

slice spec 必须是从真实 C 源码生成的中间契约和证据锚点，而不是主要由人工填写的翻译输入。

#### Scenario: L1-passed slice is accepted
- **WHEN** `auto_migrate` receives a slice spec for a target with accepted L1 native evidence
- **THEN** it records `target_id`, `slice_id`, source root, source commit, C files, function names, signatures, compile profile, fixture contract, Rust output boundary, and evidence output root before translation starts

#### Scenario: Real source extraction precedes translation
- **WHEN** a user or agent requests automatic translation for a C repository, build profile, and function selector
- **THEN** the system opens the referenced C source files, uses a real C-aware frontend or parser plus compile-profile evidence to locate the function boundary, and generates the slice spec from the extracted source span
- **AND** the generated slice spec records source file path, line or byte span, source hash, source commit, compile command source, include paths, defines, macro or preprocessing mode, function signature, direct callees, and unsupported extraction facts before translation starts
- **AND** a hand-authored `c_source` string without real source file, span, hash, and compile-profile provenance MUST NOT satisfy this requirement

#### Scenario: Slice spec remains the downstream contract
- **WHEN** the source extractor emits a slice spec
- **THEN** context pack, type map, CFG, pointer graph, Rust draft, C oracle harness, Rust replay test, cache metadata, and final L3 evidence all consume the same slice spec hash
- **AND** any manual override to the generated slice spec records the edited fields, reason, reviewer, previous hash, new hash, and verification rerun requirements before the run can be accepted

#### Scenario: Missing L1 evidence blocks translation
- **WHEN** the slice spec references a target without accepted L1 native evidence
- **THEN** the automatic translation run stops before generating Rust code and writes a blocked reason to `validation/evidence/<target>/l3-<slice>-blocked-repairs.json`

#### Scenario: Build profile records semantic inputs
- **WHEN** the slice spec is normalized
- **THEN** the build profile records include paths, defines, target triple or ABI assumption, compiler command source, preprocessing mode, tool versions, and whether clang-backed type extraction was available

#### Scenario: Platform-dependent slices declare their boundary
- **WHEN** a slice depends on RTOS APIs, hardware registers, volatile behavior, power-loss recovery, filesystem behavior, or thread/interrupt interactions
- **THEN** the build profile or slice contract MUST declare a mockable platform contract, accepted target evidence, or L4 refusal before the Rust draft can be accepted

#### Scenario: Syntax index cannot replace semantic evidence
- **WHEN** `tree-sitter-c` or another syntax-only parser locates a function, call, type spelling, or source span
- **THEN** the run may use that parser only for indexing, slicing, or tolerant scanning
- **AND** typedef, macro expansion, ABI, struct layout, integer width, implicit cast, and declaration disambiguation facts MUST come from build profile, compile commands, `CLANG_PATH`-driven clang AST dump JSON, WSL/Linux/CI evidence, or explicit unsupported/type-ambiguity records before a Rust draft can be accepted

### Requirement: Real C Frontend Before Scale Claims
The system SHALL not claim scalable C-to-Rust translation capability until at least one real source function is automatically discovered, extracted, translated, and validated through the existing evidence gates.

系统在至少一个真实源码函数完成自动发现、抽取、翻译并通过现有证据门禁之前，不得声明具备可规模化的 C-to-Rust 翻译能力。
#### Scenario: Corrode-style frontend lesson is adopted
- **WHEN** the project compares its pipeline with Corrode-style C-to-Rust translation
- **THEN** the project treats Corrode's useful lesson as the need for a real C source frontend that can consume compiler-like inputs, preprocessing context, and parsed C structure before emitting Rust candidates
- **AND** the project does not copy Corrode's broad unsafe-first output strategy as sufficient for acceptance
- **AND** low unsafe ratio, oracle/replay equivalence, negative controls, compile self-healing evidence, cache/version binding, and OpenSpec validation remain mandatory

#### Scenario: L1 target count is not translation evidence
- **WHEN** reporting automatic translation progress
- **THEN** L1 native build/test success for a target is reported only as C baseline reproducibility
- **AND** it MUST NOT be used as evidence that the translator can automatically translate that target's real functions
- **AND** translation capability is reported only for named real-source functions or slices with generated slice spec provenance and completed L3 evidence

### Requirement: Context Type CFG And Pointer Evidence
The system SHALL extract and persist context pack, type map, CFG, and pointer graph evidence before generating a Rust draft.

系统必须在生成 Rust draft 之前抽取并保存 context pack、type map、CFG 和 pointer graph 证据。

#### Scenario: Context artifacts are emitted before code generation
- **WHEN** an automatic translation run prepares a slice
- **THEN** it writes `l3-<slice>-context-pack.json`, `l3-<slice>-type-map.json`, `l3-<slice>-cfg.json`, and `l3-<slice>-pointer-graph.json` under the target evidence root

#### Scenario: Type map records uncertainty
- **WHEN** typedef, macro, integer width, struct layout, enum value, pointer mutability, or implicit cast information cannot be proven from the build profile
- **THEN** `l3-<slice>-type-map.json` records the uncertainty and the translation run marks the affected node as unsupported or requiring review

#### Scenario: CFG unsupported control flow is explicit
- **WHEN** the C slice contains goto, switch fallthrough, setjmp/longjmp, computed goto, inline assembly, or another unsupported control-flow form
- **THEN** `l3-<slice>-cfg.json` records the control-flow construct and the translator refuses to claim an automatically translated Rust draft for that function unless a CFG/relooper implementation supports it

#### Scenario: Pointer graph gates pointer-bearing slices
- **WHEN** the C slice contains input pointers, output pointers, pointer arithmetic, array decay, struct field address-taking, or returned pointers
- **THEN** `l3-<slice>-pointer-graph.json` records pointer nodes, read/write effects, aliases known from the slice, promotions, raw pointer fallbacks, and unsupported alias edges before any safe wrapper is accepted

### Requirement: Deterministic Candidate Route Is Not Acceptance
The system SHALL allow scalar-only `GenericTypedIr` candidates with `token_cost=0` to be classified as `route_decision.level=L0` only for deterministic candidate routing and context-budget provenance.

The route level SHALL NOT prove semantic equivalence, SHALL NOT set `semantic_pass`, and SHALL NOT bypass validation gates for the exact generated draft.

系统可以把 scalar-only 且 `token_cost=0` 的 `GenericTypedIr` candidate 分类为 `route_decision.level=L0`，但该分类只表示 deterministic candidate routing 和上下文预算 provenance。

该 route level 不得证明语义等价，不得设置 `semantic_pass`，也不得绕过 exact generated draft 的 validation gates。

#### Scenario: Zero-token scalar candidate records L0 route
- **WHEN** `auto_migrate` receives generated typed IR candidate evidence whose route is `GenericTypedIr`, whose candidate route records `token_cost=0`, and whose pointer graph has no pointer surface
- **THEN** it may record `route_decision.level=L0`
- **AND** the route rationale records deterministic typed IR candidate generation
- **AND** `candidate_generation.typed_ir.semantic_pass` remains `false`
- **AND** `validation_profile.generated_draft_semantic_pass` remains `false`

#### Scenario: Risk floors override L0 deterministic routing
- **WHEN** a generated `GenericTypedIr` candidate has pointer surface, blocked alias risk, requires-noalias risk, unknown alias risk, or unknown pointer ownership
- **THEN** the route decision keeps the existing L1/L2/L3 risk floor instead of downgrading the slice to L0
- **AND** the typed IR candidate provenance remains recorded in the rationale

#### Scenario: Route L0 does not bypass acceptance gates
- **WHEN** a generated Rust draft compiles and the route decision is L0
- **THEN** semantic acceptance still requires the selected validation profile to pass with no skipped required gate
- **AND** C oracle, Rust replay, schema-aware diff, negative diff, unsafe evidence, cache/version binding, and final verification remain authoritative for semantic-pass claims

### Requirement: Rust Draft Generation
The system SHALL generate a Rust draft only for the supported C subset and SHALL distinguish low-level raw pointer draft details from safe Rust public API boundaries.

系统必须只为已支持的 C 子集生成 Rust draft，并且必须区分低层 raw pointer draft 与 safe Rust public API 边界。

#### Scenario: Supported structured function generates draft
- **WHEN** the slice contains supported primitive expressions, assignments, returns, calls, if/while/for control flow, and supported pointer patterns
- **THEN** the translator writes a Rust draft artifact and records source spans, generated Rust spans, unsupported node count, unsafe candidate count, and translation rule ids in `l3-<slice>-auto-translation-plan.json`

#### Scenario: Public API does not expose raw pointers by default
- **WHEN** the translator generates a Rust-facing public function for a pointer-bearing C slice
- **THEN** the public boundary uses a safe wrapper, validated buffer, newtype, or explicit internal FFI boundary instead of exposing raw pointers unless the slice contract records a reviewed exception

#### Scenario: Unsupported C does not produce false success
- **WHEN** the translator encounters unsupported syntax or semantics
- **THEN** the run writes the unsupported node, source span, reason, and required future capability to `l3-<slice>-auto-translation-events.jsonl` and does not mark the translation gate as passed

#### Scenario: Route and refusal metrics are emitted
- **WHEN** an automatic translation run records route/profile/final-verification evidence
- **THEN** the run also emits route/refusal metrics by C construct, route level, candidate source, project, and slice, including generated, blocked, refused, accepted counts and dominant failure reasons

### Requirement: Oracle Harness And Rust Replay Test Generation
The system SHALL generate a C oracle harness draft and Rust replay test draft from the same slice spec and fixture contract.

系统必须从同一个 slice spec 与 fixture contract 生成 C oracle harness 初稿和 Rust replay test 初稿。

#### Scenario: C oracle harness draft is generated
- **WHEN** the slice spec maps fixture cases to C function inputs and observable outputs
- **THEN** the tool writes a C oracle harness draft, records its source path and compile command, and produces `l3-<slice>-c-oracle.json` only after the harness runs successfully in an accepted Linux, WSL, or CI environment

#### Scenario: Local C oracle skip is not success
- **WHEN** the local host cannot build or run the C oracle
- **THEN** the evidence records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and the semantic gate remains unpassed until accepted C oracle evidence records `C_ORACLE_GENERATED`

#### Scenario: Rust replay test draft is generated
- **WHEN** the same fixture contract can be mapped to the Rust draft API
- **THEN** the tool writes a Rust replay test draft, records the generated test path, and emits `l3-<slice>-test-translation.json` linking C fixture cases to Rust assertions

### Requirement: Compile Self-Healing Loop
The system SHALL drive compile self-healing from rustc JSON error stacks using bounded PatchPlan evidence before any automatic patch is applied.

系统必须基于 rustc JSON error stack 执行有边界的编译自愈，并且必须在自动打补丁前生成 PatchPlan 证据。

#### Scenario: Compiler errors are classified
- **WHEN** `cargo check --message-format=json` fails for a generated Rust draft
- **THEN** the run stores error code, primary span, related spans, rendered message, root cause key, affected generated item, retry command, and source translation rule id in `l3-<slice>-rust-check.json`

#### Scenario: PatchPlan precedes patch
- **WHEN** an error is eligible for automatic repair
- **THEN** the system writes a PatchPlan entry with patch id, files, spans, reason, expected error delta, forbidden changes, rollback id, AI usage, and verification commands before applying the patch

#### Scenario: Automatic repair is bounded
- **WHEN** compile self-healing runs for a slice
- **THEN** it performs no more than the configured retry limit, defaults to three repair rounds, and appends every attempt to `l3-<slice>-auto-translation-events.jsonl`

#### Scenario: Unsafe or semantic widening blocks repair
- **WHEN** a candidate repair changes the C oracle contract, fixture expected behavior, accepted differences, public API outside the impact set, source slice boundary, or first-party non-test unsafe budget
- **THEN** the system refuses the patch and records the reason in `l3-<slice>-blocked-repairs.json`

### Requirement: AI Candidate Boundaries
The system SHALL treat AI output as a candidate generation aid only and SHALL not use AI output as evidence of correctness.

系统必须把 AI 输出仅作为候选生成或修复建议，不得把 AI 输出当作正确性证据。

#### Scenario: AI usage is recorded
- **WHEN** AI is used to propose a Rust draft, PatchPlan, or repair candidate
- **THEN** the system writes `l3-<slice>-ai-candidate-manifest.json` with prompt scope, input artifact hashes, model or provider label when available, output hash, whether the candidate was applied, and the verification gates that accepted or rejected it

#### Scenario: AI prompt context is bounded
- **WHEN** AI assistance is requested
- **THEN** the prompt contains only the slice spec, root-cause summary, relevant source spans, type map excerpts, pointer graph excerpts, direct caller/callee facts, and current verification delta unless a recorded two-hop expansion is justified

#### Scenario: Online AI provider is optional
- **WHEN** no DeepSeek or other online AI provider is configured
- **THEN** the default local pipeline continues with deterministic translator rules or records `AI_SKIPPED` in `l3-<slice>-ai-candidate-manifest.json`
- **AND** missing AI provider availability MUST NOT fail non-AI gates such as slice spec validation, context extraction, type/CFG/pointer evidence generation, rust check, C oracle, Rust replay, diff, unsafe scan, cache binding, or OpenSpec validation

### Requirement: Final L3 Evidence Manifest
The system SHALL accept an automatic translation run only when the generated artifacts are bound into the existing L3 evidence manifest and all required gates pass.

系统只有在自动翻译生成物进入现有 L3 evidence manifest 且所有必需门禁通过时，才能接受该自动翻译 run。

#### Scenario: Manifest references translation artifacts
- **WHEN** an automatic translation run reaches final verification
- **THEN** the L3 evidence manifest references context pack, type map, CFG, pointer graph, translation plan, translation events, AI candidate manifest if any, C oracle, Rust report, diff, negative diff, rust check, unsafe scan, unsafe ledger, version manifest, cache metadata, blocked repairs, and final verification

#### Scenario: Correctness gates remain mandatory
- **WHEN** the Rust draft compiles and tests pass
- **THEN** the run is still rejected unless C oracle generation, Rust replay, schema-aware diff, negative diff, unsafe scan, version/config binding, and OpenSpec validation pass for the same slice commit and fixture hash

#### Scenario: Unsafe budget is enforced
- **WHEN** final verification computes first-party non-test unsafe usage for the generated or edited Rust code
- **THEN** the run fails if the unsafe ratio is 10% or higher, or if any unsafe usage lacks ledger evidence and test coverage

#### Scenario: Performance evidence is explicit but not semantic proof
- **WHEN** a new L3 named slice has no performance-smoke evidence
- **THEN** the manifest MUST record `performance_not_claimed`
- **AND** performance evidence MUST NOT replace C oracle, Rust replay, diff, negative diff, unsafe, version/cache, or OpenSpec gates

### Requirement: Traceable Cache Invalidation
The system SHALL invalidate reusable translation artifacts when source, toolchain, schema, profile, fixture, or AI candidate inputs drift.

系统必须在源码、工具链、schema、profile、fixture 或 AI 候选输入漂移时使可复用翻译产物失效。

#### Scenario: Cache key includes translation inputs
- **WHEN** translation artifacts are generated
- **THEN** cache metadata includes source commit, source file hashes, slice spec hash, fixture hash, build profile hash, Cargo.lock hash, rustc/cargo/OpenSpec versions, translator crate version, schema versions, and command arguments

#### Scenario: Drift invalidates previous results
- **WHEN** any cache key input changes
- **THEN** cached context pack, type map, CFG, pointer graph, Rust draft, PatchPlan, AI candidate, C oracle, diff, and final summary are not reused without regeneration or explicit evidence review

### Requirement: Bounded Pointer Arithmetic Output Write Translation
The system SHALL translate `*(base + index) = expr` as a safe output-buffer write only when the pointer, index, expression, and loop bound are proven inside the supported bounded subset.

系统必须仅在 pointer、index、expression 和 loop bound 均已由受限子集证明时，才把 `*(base + index) = expr` 翻译为 safe Rust output-buffer write。

#### Scenario: Proven pointer arithmetic output write generates safe Rust
- **WHEN** a slice writes `*(out + i) = expr` to a non-const output pointer parameter inside a loop whose condition proves `0 <= i < len` or `i < len`
- **THEN** the translator emits a Rust draft whose public boundary does not expose raw pointers
- **AND** the generated Rust write uses a safe mutable slice-style access such as `out[i as usize] = expr`
- **AND** `l3-<slice>-auto-translation-plan.json` includes the `bounded-pointer-arithmetic-output-write` rule id
- **AND** no first-party Rust unsafe is required for the public boundary

#### Scenario: Pointer graph preserves raw and canonical write evidence
- **WHEN** the translator accepts a bounded `*(out + i)` output write
- **THEN** `l3-<slice>-pointer-graph.json` records `out` as an output buffer node with `len` as its length companion
- **AND** the write evidence records the raw source expression `*(out + i)`
- **AND** the canonical write evidence records `out[i]`
- **AND** the boundary decision records the `bounded-pointer-arithmetic-output-write` rule id

#### Scenario: Unsupported pointer arithmetic writes do not produce false success
- **WHEN** `*(out + i) = expr` appears without a proven loop bound, with a non-simple base, with a non-simple index, with side effects, with a cast, with compound assignment, or with a mismatched length companion
- **THEN** the translator records an unsupported node and reason in `l3-<slice>-auto-translation-events.jsonl`
- **AND** it does not mark the automatic translation gate as passed
- **AND** it does not emit a false-success Rust draft

#### Scenario: Output write is not an input read capability
- **WHEN** a C statement writes through pointer arithmetic, including `*(out + i) = value`
- **THEN** the translator does not label the statement as an accepted input-buffer read
- **AND** pointer read effects and pointer write effects remain distinct in CFG and pointer graph evidence

#### Scenario: Existing pointer capabilities remain unchanged
- **WHEN** a slice uses the already supported `out[0]`, `values[i]`, or `*(values + i)` patterns
- **THEN** the translator preserves the existing safe boundary, evidence fields, rule ids, and generated Rust behavior for those patterns

## MODIFIED Requirements

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

#### Scenario: Bounded input buffer slice records read and length decisions
- **WHEN** a C slice reads `values[i]` from a `const T*` input buffer under a proven `0 <= i < len` loop and writes the aggregate result to `out[0]`
- **THEN** the CFG evidence records a bounded buffer-read statement, the loop condition, the length companion, and the output pointer write
- **AND** the pointer graph records `values` as a read-only input buffer, `len` as the companion bound, `out` as a write-only output pointer, and aliasing as unsupported unless separately proven
- **AND** the generated Rust draft or replay evidence records that the public boundary avoided raw pointer exposure

### Requirement: Rust Draft Generation
The system SHALL generate a Rust draft only for the supported C subset and SHALL distinguish low-level raw pointer draft details from safe Rust public API boundaries.

系统必须只为已支持的 C 子集生成 Rust draft，并且必须区分低层 raw pointer draft 与 safe Rust public API 边界。

#### Scenario: Supported structured function generates draft
- **WHEN** the slice contains supported primitive expressions, assignments, returns, calls, if/while/for control flow, and supported pointer patterns
- **THEN** the translator writes a Rust draft artifact and records source spans, generated Rust spans, unsupported node count, unsafe candidate count, and translation rule ids in `l3-<slice>-auto-translation-plan.json`

#### Scenario: Public API does not expose raw pointers by default
- **WHEN** the translator generates a Rust-facing public function for a pointer-bearing C slice
- **THEN** the public boundary uses a safe wrapper, validated buffer, newtype, or explicit internal FFI boundary instead of exposing raw pointers unless the slice contract records a reviewed exception

#### Scenario: Bounded input buffer generates safe Rust slice boundary
- **WHEN** the translator accepts a `const T* values, int len` input buffer pattern with a proven bounded loop
- **THEN** the Rust-facing public boundary uses a safe slice-like input representation and records the translation rule id for bounded input-buffer reads
- **AND** the run does not expose `*const T` in the public Rust API

#### Scenario: Unsupported C does not produce false success
- **WHEN** the translator encounters unsupported syntax or semantics
- **THEN** the run writes the unsupported node, source span, reason, and required future capability to `l3-<slice>-auto-translation-events.jsonl` and does not mark the translation gate as passed

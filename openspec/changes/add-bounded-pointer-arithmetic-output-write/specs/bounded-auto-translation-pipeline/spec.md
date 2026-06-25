## ADDED Requirements

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

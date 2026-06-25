## ADDED Requirements

### Requirement: Bounded Pointer Arithmetic Input Read Translation
The system SHALL translate `*(base + index)` as a safe input-buffer read only when the pointer, index, and loop bound are proven inside the supported bounded subset.

系统必须仅在 pointer、index 和 loop bound 均已被当前受限子集证明时，才把 `*(base + index)` 翻译为 safe Rust input-buffer read。

#### Scenario: Proven pointer arithmetic read generates safe Rust
- **WHEN** a slice reads `*(values + i)` from a read-only pointer parameter inside a loop whose condition proves `0 <= i < len` or `i < len`
- **THEN** the translator emits a Rust draft whose public boundary does not expose raw pointers
- **AND** the generated Rust read uses a safe slice-style access such as `values[i as usize]`
- **AND** `l3-<slice>-auto-translation-plan.json` includes `bounded-pointer-arithmetic-input-read` and `bounded-input-buffer-read` rule ids

#### Scenario: Pointer graph preserves raw and canonical read evidence
- **WHEN** the translator accepts a bounded `*(values + i)` input read
- **THEN** `l3-<slice>-pointer-graph.json` records `values` as a read-only buffer node with `len` as its length companion
- **AND** the read evidence records the raw source expression `*(values + i)`
- **AND** the canonical read evidence records `values[i]`
- **AND** no first-party Rust unsafe is required for the public boundary

#### Scenario: Unsupported pointer arithmetic does not produce false success
- **WHEN** `*(values + i)` appears without a proven loop bound, with a non-simple base, with a non-simple index, with side effects, with a cast, or in a write context such as `*(out + i) = value`
- **THEN** the translator records an unsupported node and reason in `l3-<slice>-auto-translation-events.jsonl`
- **AND** it does not mark the automatic translation gate as passed
- **AND** it does not emit a false-success Rust draft

#### Scenario: Existing array-index input reads remain accepted
- **WHEN** a slice reads `values[i]` under the already supported bounded loop pattern
- **THEN** the translator preserves the existing `bounded-input-buffer-read` behavior, evidence fields, and safe Rust lowering

#### Scenario: Bounded pointer arithmetic read is not a pointer write capability
- **WHEN** a C statement writes through pointer arithmetic, including `*(out + i) = value`
- **THEN** the translator continues to classify the lvalue as unsupported unless a separate future capability proves that write pattern
- **AND** the statement is not labeled as an accepted input-buffer read

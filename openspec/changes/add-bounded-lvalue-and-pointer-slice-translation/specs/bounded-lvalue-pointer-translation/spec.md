## ADDED Requirements

### Requirement: LValue Classification Is Bounded
The translator SHALL classify assignment targets before emitting Rust and SHALL only accept lvalue forms that are explicitly supported by the bounded subset.

翻译器必须先分类赋值目标，再决定是否生成 Rust；只有明确纳入 bounded subset 的 lvalue 形式才能通过。

#### Scenario: Simple identifier remains supported
- **WHEN** a C statement assigns to a simple identifier such as `value = value + 1;`
- **THEN** the translator classifies the target as a simple identifier lvalue
- **AND** the generated Rust draft preserves the existing assignment behavior

#### Scenario: Pointer field write is classified
- **WHEN** a C statement assigns to a pointer field such as `addr->sin_family = AF_INET;`
- **THEN** the translator classifies the target as a pointer field lvalue
- **AND** the pointer graph records the base pointer and field write effect

#### Scenario: Dereference identifier write is classified
- **WHEN** a C statement assigns to a dereferenced pointer identifier such as `*out = value;`
- **THEN** the translator classifies the target as a dereference identifier lvalue
- **AND** the pointer graph records a write through the pointer base

#### Scenario: Unsupported complex lvalue is blocked
- **WHEN** a C statement assigns to an unsupported lvalue such as `s.field = value;`, `arr[i] = value;`, or `*(out + i) = value;`
- **THEN** the translator does not emit a Rust draft
- **AND** it records an unsupported lvalue error with the source statement

### Requirement: Pointer Index Writes Require Bounded Evidence
The translator SHALL only accept pointer index writes when the index boundary is trivial or explicitly proven by the slice context.

翻译器只有在索引边界是平凡常量或能从 slice 上下文明确证明时，才能接受 pointer index write。

#### Scenario: Constant zero pointer index is accepted for out parameter
- **WHEN** a C function has an output pointer parameter and writes `out[0] = value;`
- **THEN** the translator classifies the target as a bounded pointer index lvalue
- **AND** the pointer graph records the write effect as `out[0]`
- **AND** the generated plan records a bounded pointer-index translation rule

#### Scenario: Unproven variable index is blocked
- **WHEN** a C function writes `out[i] = value;` without a proven bound for `i`
- **THEN** the translator does not emit a Rust draft
- **AND** it records that the pointer index boundary is unproven

#### Scenario: Pointer arithmetic is blocked
- **WHEN** a C function writes through pointer arithmetic such as `*(out + i) = value;`
- **THEN** the translator does not emit a Rust draft
- **AND** it records that pointer arithmetic is outside the bounded subset

### Requirement: Pointer Public Boundary Remains Safe
The translator SHALL preserve the safe public Rust boundary for pointer-bearing C functions and SHALL NOT expose raw pointer parameters by default.

包含指针参数的 C 函数必须继续生成安全 Rust 公共边界；默认不得暴露 raw pointer 参数。

#### Scenario: Pointer field write keeps safe wrapper
- **WHEN** a pointer-bearing C slice writes through an output pointer field
- **THEN** the generated Rust public function uses a safe wrapper or report type
- **AND** the generated Rust draft does not expose `*mut` in the public function signature

#### Scenario: Unsupported pointer alias blocks translation
- **WHEN** pointer writes include aliasing that cannot be proven from the slice context
- **THEN** the translator blocks the draft before claiming a safe wrapper candidate
- **AND** the blocked reason is recorded in pointer graph or translation events

## ADDED Requirements

### Requirement: Bounded Direct Call Expression Translation
The system SHALL translate and record bounded direct call expressions in return expressions, primitive declaration initializers, and assignment right-hand sides without claiming callee semantic equivalence.

系统必须翻译并记录受限 direct call expression，覆盖 return expression、primitive declaration initializer 和 assignment RHS，同时不得声明 callee 本身已经完成语义等价验证。

#### Scenario: Direct call expression is translated and recorded
- **WHEN** the translator processes a bounded C slice containing `return helper(value);`, `int next = helper(value);`, or `value = helper(value);`
- **THEN** the Rust draft preserves the direct call expression with Rust-compatible syntax
- **AND** the CFG records `call_expression`
- **AND** the translation plan records `bounded-call-expression`
- **AND** the evidence records the callee name and argument expressions as candidate context, not as callee semantic proof

#### Scenario: Unsupported call expression forms are blocked
- **WHEN** the translator encounters a function pointer call, member call, macro-like complex callee, nested call, or side-effecting call argument outside the bounded subset
- **THEN** the translator records `unsupported_syntax`
- **AND** it does not emit a Rust draft that could be mistaken for accepted semantic translation

#### Scenario: Simple call statements remain stable
- **WHEN** the translator processes an existing simple call statement such as `observe(value);`
- **THEN** the statement remains classified as `simple_call`
- **AND** the translation plan continues to record `simple-call`
- **AND** the new call expression rule does not change simple call statement behavior

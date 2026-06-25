## ADDED Requirements

### Requirement: Call Expression Evidence Binding
The bounded auto-translation pipeline SHALL preserve call expression evidence when accepted L3 evidence is bound to an auto-generated candidate.

自动翻译管线在把 accepted L3 evidence 绑定到 auto-generated candidate 时，必须保留 call expression evidence。

#### Scenario: Accepted call expression evidence is bound
- **WHEN** a call-expression slice has accepted C oracle, Rust replay, diff, unsafe, and final verification evidence
- **THEN** the auto evidence manifest records semantic pass through the accepted evidence binding
- **AND** the normalized plan and context pack retain direct call expression evidence
- **AND** missing call expression evidence causes the slice-specific L3 evidence test to fail

## ADDED Requirements

### Requirement: Auto-Translated Slice Evidence Source
The system SHALL allow FlashDB or non-FlashDB L3 migration loops to consume auto-translated Rust draft artifacts only as evidence-bound candidates, not as accepted implementation by default.

系统可以让 FlashDB 或非 FlashDB 的 L3 迁移循环消费自动翻译生成的 Rust draft，但这些生成物默认只能作为绑定证据的候选，不能自动视为已接受实现。

#### Scenario: Auto-generated draft is marked as candidate
- **WHEN** an L3 migration slice uses artifacts from the bounded automatic translation pipeline
- **THEN** the slice evidence records generated source paths, generator version, input slice spec hash, build profile hash, translation rule ids, AI candidate manifest if any, and candidate status before validation

#### Scenario: L3 gate remains authoritative
- **WHEN** an auto-generated Rust draft compiles
- **THEN** the L3 migration loop still requires C oracle, Rust replay, schema-aware diff, negative diff, unsafe scan, version manifest, cache metadata, and final verification evidence before accepting the slice

### Requirement: Auto-Translation Evidence Manifest Binding
The system SHALL bind auto-translation artifacts into the existing L3 evidence manifest without weakening existing FlashDB L3 gates.

系统必须把自动翻译产物绑定进现有 L3 evidence manifest，并且不得削弱现有 FlashDB L3 门禁。

#### Scenario: Manifest includes translator-specific artifacts
- **WHEN** an L3 evidence manifest is emitted for an auto-translated slice
- **THEN** it includes or references `l3-<slice>-auto-translation-plan.json`, `l3-<slice>-auto-translation-events.jsonl`, `l3-<slice>-type-map.json`, `l3-<slice>-cfg.json`, `l3-<slice>-patch-events.jsonl` or equivalent PatchPlan evidence, and `l3-<slice>-blocked-repairs.json`

#### Scenario: Missing translator artifacts fail the auto-translation claim
- **WHEN** an L3 manifest claims that a slice was produced by the automatic translation pipeline
- **THEN** the claim fails if context pack, type map, CFG, pointer graph decision, Rust draft provenance, C oracle evidence, Rust replay evidence, diff evidence, unsafe evidence, and version/config binding are not all present

### Requirement: Auto-Translation Repair Boundaries
The system SHALL preserve existing FlashDB slice contracts during automatic compile self-healing.

系统在自动编译自愈过程中必须保留现有 FlashDB slice contract，不得为了通过编译而扩大语义边界。

#### Scenario: Forbidden L3 edits block self-healing
- **WHEN** compile self-healing proposes to edit FlashDB fixture expected results, C oracle contracts, accepted differences, public behavior fields, source slice boundaries, or unsafe budget policy
- **THEN** the L3 loop records a blocked repair requiring human approval and refuses to apply the patch automatically

#### Scenario: Patch verification is staged
- **WHEN** an automatic self-healing patch is applied to a generated or migrated Rust artifact
- **THEN** the L3 loop reruns compile check first, targeted Rust replay tests second, full relevant Rust tests third, then C/Rust diff, negative diff, unsafe scan, version/config checks, and OpenSpec validation unless an earlier gate blocks

## ADDED Requirements

### Requirement: L3 Bilingual OpenSpec Text Integrity
The system SHALL keep FlashDB L3 OpenSpec artifact prose readable as UTF-8 text while preserving parser-required English anchors.

系统必须保持 FlashDB L3 OpenSpec 文档说明文本为可读 UTF-8，同时保留 parser 需要的英文结构锚点。

#### Scenario: Bilingual prose remains readable
- **WHEN** the agent writes or repairs FlashDB L3 OpenSpec proposal, design, specs, tasks, summary, or evidence prose
- **THEN** Chinese explanatory text remains readable UTF-8 and does not contain known mojibake markers from encoding drift

#### Scenario: Parser anchors are preserved
- **WHEN** bilingual prose is repaired
- **THEN** OpenSpec anchors such as `## ADDED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, and `THEN` remain unchanged

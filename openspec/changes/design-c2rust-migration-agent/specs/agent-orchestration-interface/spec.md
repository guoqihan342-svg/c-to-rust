## ADDED Requirements

### Requirement: Agent runtime contract
The migration system SHALL expose an Agent contract that can be executed by OpenCode, Codex, or another compatible agent runtime. The contract SHALL define commands or tasks for propose, plan, index, migrate, repair, verify, and audit phases, and each phase SHALL be traceable to an OpenSpec change artifact.

杩佺Щ绯荤粺蹇呴』鎻愪緵鍙 OpenCode銆丆odex 鎴栧叾浠栨櫤鑳戒綋璋冪敤鐨?Agent 濂戠害锛屽苟鎶婃瘡涓樁娈电粦瀹氬埌 OpenSpec 宸ヤ欢銆?
#### Scenario: Runtime receives a migration request
- **WHEN** a user requests the FlashDB C-to-Rust migration Agent
- **THEN** the system creates or reuses an OpenSpec change before implementation work begins
- **THEN** the runtime has named tasks for indexing, skeleton generation, migration, compile repair, equivalence verification, and unsafe auditing

### Requirement: Bounded parallel subagents
The migration system SHALL allow multiple subagents for independent read-only analysis, disjoint implementation slices, verification, and review. Subagents MUST NOT edit shared files concurrently unless ownership is explicit and disjoint.

绯荤粺鍙互寮€澶氫釜瀛愭櫤鑳戒綋锛屼絾蹇呴』鏈夎竟鐣岋細鍙鍒嗘瀽鍙苟琛岋紝鍐欐搷浣滃繀椤绘寜鏂囦欢鎴栨ā鍧楅殧绂汇€?
#### Scenario: Parallel context gathering
- **WHEN** C2Rust constraints, FlashDB module scope, and testing gates can be analyzed independently
- **THEN** the orchestrator runs them as separate read-only subagent tasks
- **THEN** their outputs are merged into the OpenSpec design without direct file edits by those subagents

### Requirement: Bilingual documentation
The migration system SHALL produce durable design and operational documentation in Chinese and English. OpenSpec parser anchors such as `## ADDED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, and `THEN` MUST remain in English.

绯荤粺蹇呴』杈撳嚭涓嫳鏂囨枃妗ｏ紝浣?OpenSpec 鐨勭粨鏋勯敋鐐瑰繀椤讳繚鐣欒嫳鏂囷紝閬垮厤鏍￠獙澶辫触銆?
#### Scenario: Creating OpenSpec artifacts
- **WHEN** the Agent writes proposal, design, specs, or tasks
- **THEN** the files include Chinese and English explanatory content where useful
- **THEN** parser-required OpenSpec headings and scenario markers remain unchanged

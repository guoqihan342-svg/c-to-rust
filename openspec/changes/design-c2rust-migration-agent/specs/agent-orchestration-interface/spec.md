## ADDED Requirements

### Requirement: Agent runtime contract
The migration system SHALL expose an Agent contract that can be executed by OpenCode, Codex, or another compatible agent runtime. The contract SHALL define commands or tasks for propose, plan, index, migrate, repair, verify, and audit phases, and each phase SHALL be traceable to an OpenSpec change artifact.

迁移系统必须提供可被 OpenCode、Codex 或其他智能体调用的 Agent 契约，并把每个阶段绑定到 OpenSpec 工件。
#### Scenario: Runtime receives a migration request
- **WHEN** a user requests the FlashDB C-to-Rust migration Agent
- **THEN** the system creates or reuses an OpenSpec change before implementation work begins
- **THEN** the runtime has named tasks for indexing, skeleton generation, migration, compile repair, equivalence verification, and unsafe auditing

### Requirement: Bounded parallel subagents
The migration system SHALL allow multiple subagents for independent read-only analysis, disjoint implementation slices, verification, and review. Subagents MUST NOT edit shared files concurrently unless ownership is explicit and disjoint.

系统可以开多个子智能体，但必须有边界：只读分析可并行，写操作必须按文件或模块隔离。
#### Scenario: Parallel context gathering
- **WHEN** C2Rust constraints, FlashDB module scope, and testing gates can be analyzed independently
- **THEN** the orchestrator runs them as separate read-only subagent tasks
- **THEN** their outputs are merged into the OpenSpec design without direct file edits by those subagents

### Requirement: Bilingual documentation
The migration system SHALL produce durable design and operational documentation in Chinese and English. OpenSpec parser anchors such as `## ADDED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, and `THEN` MUST remain in English.

系统必须输出中英文文档，但 OpenSpec 的结构锚点必须保留英文，避免校验失败。
#### Scenario: Creating OpenSpec artifacts
- **WHEN** the Agent writes proposal, design, specs, or tasks
- **THEN** the files include Chinese and English explanatory content where useful
- **THEN** parser-required OpenSpec headings and scenario markers remain unchanged

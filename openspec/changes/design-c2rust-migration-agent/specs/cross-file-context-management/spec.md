## ADDED Requirements

### Requirement: Local structured context store
The migration system SHALL maintain a local SQLite and JSONL context store for files, symbols, call edges, type layouts, macro/cfg facts, pointer facts, Rust items, error events, patch events, test traces, and unsafe ledger entries.

系统必须本地优先建立结构化上下文库，避免每次把全仓库交给 AI。
#### Scenario: Indexing a C repository
- **WHEN** the Agent indexes FlashDB
- **THEN** it records symbols, calls, macros, type layouts, pointer facts, and tests with file spans and file hashes
- **THEN** every stored fact includes source tool, source version, schema version, confidence, and source commit

### Requirement: Token-bounded context packs
The migration system SHALL generate a minimal context pack for each migration or repair action. The default context pack MUST include only the target item, owning module, direct callers/callees, public type definitions, macro/cfg facts, pointer facts, related tests, current diff, and structured rustc errors.

每次 AI 调用必须使用裁剪后的 ContextPack，默认 1-hop，只在必要时扩到 2-hop。
#### Scenario: Repairing a borrow-checker error
- **WHEN** rustc reports a borrow or lifetime error in a migrated function
- **THEN** the Agent builds a context pack from the target function and directly related facts
- **THEN** the Agent expands to 2-hop context only if direct facts cannot explain the error

### Requirement: Module relationship preservation
The migration system SHALL preserve module call relationships during single-point incremental refactors. Cross-module signature changes MUST be preceded by an impact set that lists affected callers, callees, adapters, tests, and API contracts.

单点渐进式重构不能破坏模块调用关系。跨模块签名变化必须先有影响集。
#### Scenario: Signature migration crosses module boundary
- **WHEN** a migrated Rust signature requires caller changes outside the target module
- **THEN** the Agent produces an impact set before editing
- **THEN** the Agent updates adapters or callers only within the approved impact set

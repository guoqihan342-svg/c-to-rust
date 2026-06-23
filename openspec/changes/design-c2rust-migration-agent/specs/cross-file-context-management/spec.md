## ADDED Requirements

### Requirement: Local structured context store
The migration system SHALL maintain a local SQLite and JSONL context store for files, symbols, call edges, type layouts, macro/cfg facts, pointer facts, Rust items, error events, patch events, test traces, and unsafe ledger entries.

绯荤粺蹇呴』鏈湴浼樺厛寤虹珛缁撴瀯鍖栦笂涓嬫枃搴擄紝閬垮厤姣忔鎶婂叏浠撳簱浜ょ粰 AI銆?
#### Scenario: Indexing a C repository
- **WHEN** the Agent indexes FlashDB
- **THEN** it records symbols, calls, macros, type layouts, pointer facts, and tests with file spans and file hashes
- **THEN** every stored fact includes source tool, source version, schema version, confidence, and source commit

### Requirement: Token-bounded context packs
The migration system SHALL generate a minimal context pack for each migration or repair action. The default context pack MUST include only the target item, owning module, direct callers/callees, public type definitions, macro/cfg facts, pointer facts, related tests, current diff, and structured rustc errors.

姣忔 AI 璋冪敤蹇呴』浣跨敤瑁佸壀鍚庣殑 ContextPack锛岄粯璁?1-hop锛屽彧鍦ㄥ繀瑕佹椂鎵╁埌 2-hop銆?
#### Scenario: Repairing a borrow-checker error
- **WHEN** rustc reports a borrow or lifetime error in a migrated function
- **THEN** the Agent builds a context pack from the target function and directly related facts
- **THEN** the Agent expands to 2-hop context only if direct facts cannot explain the error

### Requirement: Module relationship preservation
The migration system SHALL preserve module call relationships during single-point incremental refactors. Cross-module signature changes MUST be preceded by an impact set that lists affected callers, callees, adapters, tests, and API contracts.

鍗曠偣娓愯繘寮忛噸鏋勪笉鑳界牬鍧忔ā鍧楄皟鐢ㄥ叧绯汇€傝法妯″潡绛惧悕鍙樺寲蹇呴』鍏堟湁褰卞搷闆嗐€?
#### Scenario: Signature migration crosses module boundary
- **WHEN** a migrated Rust signature requires caller changes outside the target module
- **THEN** the Agent produces an impact set before editing
- **THEN** the Agent updates adapters or callers only within the approved impact set

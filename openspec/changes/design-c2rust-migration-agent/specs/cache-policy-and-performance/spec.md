## ADDED Requirements

### Requirement: Agent artifact cache
The migration system SHALL support Agent-side caches for build traces, parsed source facts, context packs, C2Rust baseline artifacts, rustc error classifications, patch attempts, test results, coverage results, fuzz corpus metadata, and AI response candidates. Every cache entry MUST be keyed by source commit, file hashes, feature or macro matrix, tool versions, context schema version, command arguments, and prompt/model metadata when AI is involved.

Agent 工程缓存可以积极使用，但必须按源码、工具链、schema、命令和 AI 元数据做可追踪失效。

#### Scenario: Source file changes
- **WHEN** a C or Rust source file hash changes
- **THEN** cached facts, context packs, compile results, test results, and AI candidates depending on that file are invalidated
- **THEN** the Agent recomputes affected facts before migration or repair

### Requirement: Cached AI output is not evidence
The migration system MUST NOT treat cached AI output as correctness evidence. Cached AI output MAY be reused only as a candidate patch, summary, or diagnostic, and it MUST pass the same compile, test, equivalence, unsafe, and version gates as newly generated output.

缓存的 AI 输出不能当成事实或正确性证据，只能当候选。

#### Scenario: Reusing an AI repair candidate
- **WHEN** the Agent reuses a cached AI repair candidate
- **THEN** the candidate is applied only through a PatchPlan
- **THEN** the same compile and semantic verification gates run before the repair is accepted

### Requirement: Runtime cache boundaries
The `flashDB_rust` runtime SHALL keep caches bounded, observable, disable-able, and semantically transparent. Runtime caches MUST NOT change public behavior, persistent flash/file image layout, return codes, error mappings, GC behavior, or reopen behavior.

`flashDB_rust` 运行时缓存必须可关闭、可观测、有上限，并且不能改变持久化语义。

#### Scenario: Cache enabled versus disabled
- **WHEN** the same KVDB or TSDB operation sequence runs with runtime cache disabled and enabled
- **THEN** return codes, read values, error mappings, flash image bytes, GC state, and reopen state are equivalent
- **THEN** cache metrics record hits, misses, invalidations, and memory usage

### Requirement: Runtime cache invalidation
The `flashDB_rust` runtime SHALL invalidate affected cache entries on write, erase, format, GC, reopen, backend replacement, feature/config changes, and failed storage operations. Write-back caching MUST NOT be enabled in the first milestone unless flush, sync, erase, reopen, and crash-recovery semantics are proven equivalent to the C oracle.

运行时缓存必须在写、擦除、GC、重开和配置变化时失效。首阶段不默认启用 write-back cache。

#### Scenario: Erase invalidates cached data
- **WHEN** a storage sector is erased
- **THEN** all cache entries overlapping that sector are invalidated
- **THEN** subsequent reads observe erased-value semantics rather than stale cached bytes

### Requirement: Cache performance gates
The migration system SHALL measure cache effects with scenario counters and benchmarks. The gates MUST include cache hit rate, invalidation count, memory budget, flash read/write/erase operation counts, and scenario latency. Cache optimizations MUST be rejected when they improve speed by changing observable behavior.

缓存优化必须测量，不得为了速度改变行为。

#### Scenario: Cache optimization candidate
- **WHEN** a cache optimization is proposed
- **THEN** the Agent compares cache-disabled and cache-enabled differential tests
- **THEN** the Agent accepts the optimization only if semantic gates pass and performance counters improve or stay within configured thresholds

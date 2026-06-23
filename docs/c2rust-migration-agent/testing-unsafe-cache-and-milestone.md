# Testing, Unsafe Budget, Cache, and Performance Gates

中文说明：语义等价不能靠“看起来一样”，必须靠 C oracle/C2Rust baseline、Rust 测试、golden image、property/fuzz、覆盖率、性能 smoke 和 unsafe 审计共同约束。

English summary: semantic equivalence must be proven with machine evidence, not model judgment.

## Rust Test Stack

Required default commands:

```bash
cargo check --message-format=json
cargo test
```

Preferred extended commands when tools are installed:

```bash
cargo nextest run
cargo llvm-cov nextest
cargo fuzz run header_decode
cargo fuzz run sector_state
```

Rust testing frameworks:

- built-in Rust unit and integration tests
- `proptest` for boundary and corruption cases
- `cargo-fuzz` for parsers and persistent layout decoding
- Criterion or equivalent for performance smoke tests

## Differential Oracle

C/Rust or C2Rust/Rust differential checks must compare:

- return codes and mapped errors
- stored values and blob bytes
- iteration results where order is defined
- GC effects
- reopen behavior
- flash/file image bytes or accepted normalized forms
- operation counters such as read/write/erase counts

Accepted differences must be documented. LLM judgment is not evidence.

## Unit Test Targets

- CRC
- alignment
- header encoding/decoding
- blob encoding/decoding
- sector status transitions
- address calculations
- error/status mapping
- write granularity handling

## Integration Test Targets

- KVDB `set/get/delete`
- KVDB blob set/get
- KVDB iterate
- KVDB GC
- KVDB reopen with file-mode backend
- TSDB append
- TSDB query by time
- TSDB count
- TSDB status update

## Property and Fuzz Targets

`proptest` strategies:

- key length and value length boundaries
- capacity exhaustion
- write granularity variants
- CRC mismatch
- corrupted header/blob images
- repeated set/delete/reopen sequences

`cargo-fuzz` targets:

- header decode
- blob decode
- sector-state parsing
- TSDB record parsing

Failing generated cases must be minimized and committed as regression fixtures.

## Unsafe Budget

Scope: first-party non-test Rust code only.

Numerator:

- unsafe block LOC
- unsafe function body LOC
- raw pointer dereference or cast statements
- FFI boundary statements
- persistent layout conversion statements
- `transmute` statements

Denominator excludes:

- tests
- benches
- dependencies
- generated bindings

Gate: unsafe ratio must stay below 10%, and every unsafe item must be registered.

Whitelist:

- `ffi`
- raw flash read/write boundary when proven necessary
- persistent layout conversion
- required `#[repr(C)]` interop
- evidence-approved callback, union, or allocator boundary

Ledger fields:

- file
- span
- category
- reason
- alternative considered
- tests covering it
- source evidence

Patches fail when they add unregistered unsafe or raise unsafe above 10%.

## Cache Policy

Agent-side caches are encouraged for speed:

- build traces
- source facts
- context packs
- C2Rust artifacts
- rustc classifications
- patch attempts
- test results
- coverage results
- fuzz metadata
- AI candidates

Cache keys must include source commit, file hashes, macro/feature matrix, command arguments, tool versions, context schema version, and prompt/model metadata when AI is involved.

Runtime caches inside `flashDB_rust` must be:

- bounded
- observable
- disable-able
- semantically transparent

Invalidation must happen on write, erase, format, GC, reopen, backend replacement, feature/config changes, and failed storage operations. Write-back cache is not enabled in the first milestone unless flush, sync, erase, reopen, and crash-recovery equivalence are proven.

## Performance Gates

Measure:

- cache hit rate
- invalidation count
- memory budget
- flash read/write/erase operation counts
- scenario latency
- cache-enabled versus cache-disabled differential behavior

Performance improvements are rejected if they change public behavior, persistent layout, error mapping, GC, or reopen semantics.

## First Milestone Acceptance

The first milestone is acceptable only when:

- `flashDB_rust` builds as a Rust crate and executable.
- main KVDB paths pass Rust tests and differential tests.
- basic TSDB paths pass Rust tests and differential tests.
- memory and file-mode backends are both tested.
- golden flash/file image comparisons are recorded.
- unsafe is registered and below 10%.
- cache-disabled and cache-enabled behavior is equivalent if runtime cache exists.

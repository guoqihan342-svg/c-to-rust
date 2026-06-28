英文镜像见 `flashdb-rust-skeleton-and-milestone.en.md`。

# `flashDB_rust` Skeleton and First Milestone

中文说明：第一阶段不追求一次性迁完整个 FlashDB，而是先做可编译、可测试、可差分验证的 host-verifiable 子集。

English summary: the first milestone builds a small, compilable, host-verifiable Rust crate before broad migration.

## Showcase Boundary / 展示边界

中文说明：`flashDB_rust` 是手写安全 Rust 实现和验证基线，不是 translator-generated candidate，不能被描述成自动 C-to-Rust 管线的输出。

它的作用是先把目标 Rust API 形状、持久化行为、差分 fixture、unsafe ledger 预期和 rollback metadata 具体化，再接受更大的迁移声明。自动翻译器生成的 candidate 可以和这个基线对比，但只有 accepted evidence 证明必需门禁后才不再只是 candidate；semantic pass 由 validation profile 和 evidence gates 判定，不由这个 crate 是否存在决定。

因此 FlashDB showcase 展示的是验证边界和 milestone 形状，不声明 native-build catalogue、FlashDB project entry 或 Rust skeleton 已经代表真实项目端到端自动翻译完成。

`flashDB_rust` is a handwritten safe Rust implementation and validation baseline. It is not a translator-generated candidate and must not be described as output from the automatic C-to-Rust pipeline.

Its role is to make the desired Rust API shape, persistence behavior, differential fixtures, unsafe ledger expectations, and rollback metadata concrete before accepting broader migration claims. A translator-generated candidate can be compared against this baseline, but it remains a candidate until accepted evidence proves the required gates. A semantic pass is the outcome of validation profile plus evidence gates, not the existence of this crate.

The FlashDB showcase therefore demonstrates the intended verification boundary and milestone shape. It does not claim that the native-build catalogue, the FlashDB project entry, or the Rust skeleton means a real project has been automatically translated end to end.

## Crate Layout

```text
flashDB_rust/
  Cargo.toml
  src/
    lib.rs
    config.rs
    types.rs
    flash.rs
    port.rs
    format.rs
    kvdb.rs
    tsdb.rs
    ffi.rs
    cli.rs
  tests/
    kvdb_main_paths.rs
    tsdb_basic_paths.rs
    differential.rs
    persistence.rs
  benches/
    smoke.rs
  fuzz/
    fuzz_targets/
      header_decode.rs
      sector_state.rs
```

Module roles:

- `config`: feature flags and validated runtime options.
- `types`: `Error`, `Result<T>`, address/newtype wrappers, status enums, and public data types.
- `flash`: `FlashDevice` trait, memory backend, file-mode backend, and operation counters.
- `port`: host-specific adapters, time hooks, lock abstractions, and future platform boundaries.
- `format`: CRC, alignment, header/blob encoding, sector state, and persistent layout conversion.
- `kvdb`: Rust-native KVDB API and implementation.
- `tsdb`: basic Rust-native TSDB API and implementation.
- `ffi`: optional C ABI compatibility boundary only.
- `cli`: smoke executable for fixture replay and differential runs.

## Safe Rust API Direction

C output parameters become Rust return values:

```rust
pub fn get(&self, key: &str) -> Result<Option<Vec<u8>>>;
pub fn set(&mut self, key: &str, value: &[u8]) -> Result<()>;
pub fn delete(&mut self, key: &str) -> Result<()>;
pub fn iter(&self) -> impl Iterator<Item = Result<KvEntry<'_>>>;
```

Rust-native public APIs must not expose raw pointers. Raw C ABI patterns belong only in `ffi` and require an unsafe ledger entry.

## CLI Smoke Executable

The CLI is a validation tool, not the core product:

```bash
flashdb-rust smoke --backend memory --fixture fixtures/kvdb-basic.json
flashdb-rust diff --oracle c --fixture fixtures/kvdb-basic.json
flashdb-rust inspect-image --path target/tmp/kvdb.flash
```

Required capabilities:

- replay fixture operation sequences
- produce deterministic result JSON
- compare C oracle and Rust result JSON
- dump flash/file image hash
- report read/write/erase counters

## First Milestone Scope

Included:

- memory backend for deterministic tests
- file-mode backend for persistence smoke tests
- `Error`, `Result<T>`, `FlashAddr`, `SectorOffset`, and status enums
- CRC, alignment, header/blob encoding, address calculations
- storage read/write/erase semantics
- KVDB string/blob set, get, delete, iterate, GC, and reopen
- basic TSDB append, query, count, and status behavior

Excluded from first milestone:

- hardware flash ports
- FAL integration
- RTOS and Zephyr ports
- complete macro matrix
- all C samples and demos
- full C ABI compatibility
- runtime async or multithreaded storage semantics

## Migration Order

1. Create crate skeleton and make `cargo check` pass.
2. Add memory backend and file-mode backend.
3. Implement persistent format helpers with unit tests.
4. Implement KVDB main paths with differential fixtures.
5. Implement basic TSDB paths.
6. Add cache-disabled versus cache-enabled checks only after baseline behavior is stable.
7. Add optional FFI adapters only after Rust-native API is stable.

No migrated slice is complete until it has compile, Rust tests, differential evidence, unsafe ledger status, and rollback metadata.

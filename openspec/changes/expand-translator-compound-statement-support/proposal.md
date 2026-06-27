## Why

`crates/c2r-translator` 当前会把 `value += 1;`、`i++;`、`--i;` 这类常见 C 语句当作 unsupported expression，从而阻断很多本可安全翻译的结构化函数 slice。补齐这些语句能扩大受限自动翻译器的真实覆盖面，同时不进入复杂 CFG、宏或 pointer ownership 推断。

## What Changes

- 支持 C compound assignment 语句，例如 `+=`、`-=`、`*=`、`/=`、`%=` 以及 Rust 同样支持的位运算复合赋值。
- typed IR / clang-lowered 路径在 simple scalar variable target 上支持 clang-proven integer promotion/truncation，例如 `uint8_t value; value += 1;` 会通过 compute type 显式 cast 后再 cast 回 target type。
- 支持 standalone pre/post increment 和 decrement 语句，例如 `i++`、`++i`、`i--`、`--i`。
- 继续拒绝不在 bounded MVP 子集内的未知 expression，避免误报翻译成功。
- 更新 translator tests，证明新语句生成 Rust draft、CFG statement kind 和 translation rule evidence。

## Capabilities

### New Capabilities
- `translator-compound-statement-support`: 约束 bounded translator 可翻译常见 compound assignment 与 standalone inc/dec 语句，并保留 unsupported false-success 防线。

### Modified Capabilities
- None.

## Impact

- Affected crate: `crates/c2r-translator`.
- Affected tests: `crates/c2r-translator/tests/bounded_translation.rs`.
- Affected validation/docs: OpenSpec artifacts under this change.
- No new third-party dependencies.

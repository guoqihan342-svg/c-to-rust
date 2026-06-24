## Why

当前 L3 证据主要集中在 FlashDB 结构化输出和 L2 纯函数/工具函数，尚未用真实 pointer-bearing C 切片验证 pointer graph、config profile、code-test translation、C oracle、Rust replay、diff、negative diff、unsafe ledger 和 final verification 的完整模板链。

This change runs one real pointer-bearing L3 slice from `libuv`: `uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr)`. The slice has a C string pointer input, an output pointer, deterministic behavior, upstream tests, and an already-pinned L1 native build.

## What Changes

- Add a bounded Rust migration slice for `libuv` `uv_ip4_addr`.
- Add a Rust test-first workflow for valid IPv4, invalid IPv4, wildcard/broadcast, and port byte-order cases.
- Add a WSL/Linux C oracle generator that calls the pinned libuv build and writes machine-readable fixture/oracle evidence.
- Add Rust replay, schema-aware diff, negative diff, pointer graph, config profile, test translation, unsafe scan/ledger, performance smoke, final verification, and summary evidence for the pointer-bearing L3 slice.
- Keep the claim narrow: only the named function, pinned libuv commit, fixture input domain, and compared fields.
- Do not change FlashDB runtime, existing historical evidence, libuv upstream source, CI workflow, or event-loop/socket behavior.

## Capabilities

### New Capabilities

- `libuv-ip4-addr-pointer-l3`: Runs and verifies a real pointer-bearing L3 migration slice for libuv `uv_ip4_addr`.

### Modified Capabilities

- None.

## Impact

- Affected Rust crate: `validation/l2_slices`.
- Affected validation assets: `validation/evidence/libuv/`, `validation/l2_slices/fixtures/`, `validation/l2_slices/tools/`, and OpenSpec change artifacts.
- External dependency for oracle generation: existing pinned WSL libuv checkout and build recorded by `validation/evidence/libuv/l1-native-build.json`.
- No new third-party Rust dependencies are required.

## 1. OpenSpec

- [x] 1.1 Create proposal, design, specs, and task list for `run-libuv-ip4-addr-pointer-l3`.
- [x] 1.2 Validate the change with `openspec validate run-libuv-ip4-addr-pointer-l3 --strict`.

## 2. Test-First Rust Slice

- [x] 2.1 Add failing Rust tests for `libuv_ip4_addr` valid, invalid, wildcard, broadcast, and port byte-order cases.
- [x] 2.2 Run the targeted test and record the expected red failure.
- [x] 2.3 Implement the safe Rust `libuv_ip4_addr` slice.
- [x] 2.4 Run the targeted test and record the green result.

## 3. C Oracle and Replay Reports

- [x] 3.1 Add a WSL/Linux C oracle generator that compiles against the pinned libuv checkout/build.
- [x] 3.2 Generate `validation/l2_slices/fixtures/libuv-ip4-addr-c-oracle.json`.
- [x] 3.3 Extend Rust report emission to generate libuv IP4 Rust report, schema diff, negative diff, performance smoke, unsafe scan/ledger, and summary evidence.

## 4. L3 Template Evidence

- [x] 4.1 Add slice contract, context pack, impact set, cache metadata, config profile, pointer dependency graph, test translation, version/config binding, and evidence manifest for `libuv/l3-ip4-addr`.
- [x] 4.2 Validate pointer graph, config profile, test translation, and L3 evidence manifest JSON against their schemas.
- [x] 4.3 Confirm the L3 claim boundary excludes event-loop, socket, IPv6, DNS, whole-project migration, and whole-program alias safety.

## 5. Final Verification

- [x] 5.1 Run JSON parse/schema validation for all new evidence.
- [x] 5.2 Run `cargo fmt -- --check` and `cargo test` in `validation/l2_slices`.
- [x] 5.3 Run `openspec validate run-libuv-ip4-addr-pointer-l3 --strict` and `openspec validate --all`.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Commit and push the verified pointer-bearing L3 slice.

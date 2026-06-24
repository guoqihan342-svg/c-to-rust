## Context

The current repository already has L0/L1 evidence for many C projects and several FlashDB L3 slices. It also has reusable templates for L3 evidence, pointer dependency graph evidence, config/profile evidence, and code-test translation evidence.

The missing proof point is a real non-FlashDB pointer-bearing C slice. `libuv` is suitable because L1 has already passed at commit `5e7d51a8f4734cac453db960d4b9919735bbf7c3`, and `uv_ip4_addr` is small but pointer-heavy:

- `const char* ip`: borrowed C string pointer input.
- `int port`: value input that is converted to network byte order.
- `struct sockaddr_in* addr`: mutable output pointer written by the function.

## Goals

- Run one real pointer-bearing L3 chain end to end.
- Keep the slice small enough that every evidence file is inspectable.
- Preserve the unsafe budget: first-party non-test Rust source stays at zero `unsafe`.
- Use a real C oracle compiled against the pinned libuv build, not a hand-written C imitation.
- Exercise the new pointer graph and code-test translation templates with real slice evidence.
- Record final verification before commit and push.

## Non-Goals

- No libuv event-loop, UDP/TCP, DNS, IPv6, callback, or socket lifecycle migration.
- No whole-program alias proof.
- No claim about every platform-specific macro branch.
- No CI workflow change.
- No new runtime dependency.
- No modification of the external libuv checkout.

## Decisions

- Put the Rust slice in `validation/l2_slices`.
  - Rationale: this crate already hosts small cross-project migration slices and report emission.
  - Trade-off: the crate name still says L2, but the evidence files will explicitly record L3 for this slice.

- Generate the C oracle with WSL.
  - Rationale: the existing libuv L1 evidence was generated in WSL and records the external clone/build path.
  - Fallback: if WSL or the external checkout is missing, evidence must remain incomplete; do not replace it with a Windows-only mock oracle.

- Compare normalized fields instead of raw `sockaddr_in` memory.
  - Rationale: raw struct padding is not portable. Behavior fields are return code, address family, port bytes, host-order port, IPv4 bytes, and status.

- Keep Rust safe.
  - Rationale: Rust can represent the output pointer behavior as an owned struct returned from a function. This validates pointer-surface migration without adding unsafe.

## Evidence Layout

New or updated files will use:

- `validation/l2_slices/src/libuv_ip4_addr.rs`
- `validation/l2_slices/tests/libuv_ip4_addr.rs`
- `validation/l2_slices/tools/generate_libuv_ip4_oracle.py`
- `validation/l2_slices/fixtures/libuv-ip4-addr-c-oracle.json`
- `validation/evidence/libuv/l3-ip4-addr-*.json`

## Risks

- The external WSL libuv checkout might be missing. Mitigation: use the L1 evidence path and fail the oracle generation explicitly if absent.
- libuv return code constants may differ by platform. Mitigation: the oracle is the source of truth and the Rust implementation maps only the fixture-observed behavior.
- Raw `sockaddr_in` padding may be unstable. Mitigation: compare normalized behavior fields only.
- This slice is small. Mitigation: explicitly state it does not prove libuv networking/event-loop migration.

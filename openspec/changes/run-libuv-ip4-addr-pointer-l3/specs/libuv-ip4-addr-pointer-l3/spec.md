## ADDED Requirements

### Requirement: Pointer-bearing libuv slice boundary
The system SHALL define a bounded L3 slice for libuv `uv_ip4_addr` with explicit C pointer inputs and outputs.

#### Scenario: Slice boundary is recorded
- **WHEN** the libuv IPv4 address slice is prepared
- **THEN** the slice contract records the pinned libuv commit `5e7d51a8f4734cac453db960d4b9919735bbf7c3`
- **AND** the C boundary includes `uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr)`, `uv_inet_pton`, and the relevant upstream `test-ip4-addr` cases
- **AND** the claim boundary excludes libuv event-loop, UDP/TCP socket, IPv6, DNS, and whole-project migration behavior

### Requirement: Pointer graph validates a real pointer surface
The system SHALL record pointer dependency graph evidence for the libuv `uv_ip4_addr` slice before claiming L3 success.

#### Scenario: Pointer graph is recorded
- **WHEN** the slice reaches L3
- **THEN** the pointer graph status is `recorded`
- **AND** it includes a C string pointer input node for `ip`
- **AND** it includes an output pointer node for `struct sockaddr_in* addr`
- **AND** it records writes to `sin_family`, `sin_port`, and `sin_addr.s_addr`
- **AND** it states that the graph is dependency evidence, not whole-program alias proof

### Requirement: Native C oracle is generated from pinned libuv
The system SHALL generate C oracle evidence by compiling and running a helper against the pinned libuv checkout/build.

#### Scenario: C oracle generated
- **WHEN** oracle generation runs for the fixture corpus
- **THEN** the oracle report has status `passed`
- **AND** it records marker `C_ORACLE_GENERATED`
- **AND** each case records return code, address family, network-order port, host-order port, IPv4 bytes, and normalized status

### Requirement: Safe Rust replay matches the C oracle
The system SHALL implement a safe Rust replay for the libuv IPv4 address slice and compare it with C oracle behavior.

#### Scenario: Rust replay and diff pass
- **WHEN** Rust replay runs against the same fixture corpus
- **THEN** Rust report status is `passed`
- **AND** schema-aware diff status is `passed`
- **AND** `first_mismatch` is `null`
- **AND** compared behavior fields include return code, family, port bytes, host-order port, IPv4 bytes, and status

### Requirement: Negative diff proves mismatch detection
The system SHALL include a negative diff for the libuv pointer-bearing slice.

#### Scenario: Negative mutation is detected
- **WHEN** the expected C oracle output is mutated in a behavior field
- **THEN** the negative diff report records `expected_failure:true`
- **AND** it records `mutation_detected:true`
- **AND** it identifies the first mismatch

### Requirement: Template-chain evidence is complete
The system SHALL produce L3 evidence that exercises config profile, code-test translation, unsafe ledger, performance smoke, final verification, and summary templates.

#### Scenario: L3 evidence manifest is complete
- **WHEN** the libuv pointer-bearing slice is reported as L3
- **THEN** the L3 evidence manifest references slice contract, context pack, cache metadata, config profile, pointer dependency graph, test translation, C oracle, Rust report, schema diff, negative diff, rust check, unsafe scan, unsafe ledger, performance smoke, final verification, summary, and version/config binding artifacts
- **AND** every referenced required artifact is present with a passing or recorded status appropriate to its gate

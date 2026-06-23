## ADDED Requirements

### Requirement: Unsafe budget
The migration system SHALL keep first-party non-test Rust unsafe below 10%. The numerator SHALL include unsafe block LOC, unsafe function body LOC, raw pointer dereference/cast statements, FFI statements, layout conversion statements, and transmute statements. The denominator SHALL exclude tests, benchmarks, dependencies, and generated bindings.

first-party Rust 闈炴祴璇曚唬鐮?unsafe 蹇呴』浣庝簬 10%锛岀粺璁″彛寰勫繀椤绘槑纭€?
#### Scenario: Auditing unsafe usage
- **WHEN** the Agent completes a migration slice
- **THEN** it updates the unsafe ledger with unsafe locations, reasons, alternatives, and evidence
- **THEN** the slice fails the gate if unregistered unsafe is introduced

### Requirement: Safe public API
The migration system SHALL expose a Rust-native safe public API that does not expose raw pointers. Any required C ABI compatibility MUST be isolated behind an explicit FFI layer.

Rust-native public API 涓嶈兘鏆撮湶瑁告寚閽堬紱C ABI 鍏煎鍙兘鍦?FFI 灞傘€?
#### Scenario: Migrating an output parameter API
- **WHEN** a C function returns data through output parameters
- **THEN** the Rust-native API represents it with `Result`, `Option`, slices, iterators, or structured return values
- **THEN** raw pointer output parameters remain only in a documented FFI adapter if required

### Requirement: Unsafe whitelist
The migration system SHALL allow unsafe only in whitelisted zones: `ffi`, flash raw read/write, persistent layout conversion, required `#[repr(C)]` interop, and evidence-approved callback, union, or allocator boundaries.

unsafe 鍙兘鍑虹幇鍦ㄧ櫧鍚嶅崟鍖哄煙锛屽苟涓旀瘡澶勯兘瑕佹湁璇佹嵁銆?
#### Scenario: Unsafe outside the whitelist
- **WHEN** a patch adds unsafe outside an approved zone
- **THEN** the Agent rejects the patch or marks the task incomplete
- **THEN** the unsafe ledger records the rejection and required redesign

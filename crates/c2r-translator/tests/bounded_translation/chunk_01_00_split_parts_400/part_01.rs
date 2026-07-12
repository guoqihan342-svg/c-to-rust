#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_alignof_int_with_target_alignment_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        int_align: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "alignof_int_bytes",
        Some(&target_abi),
    )
    .expect("lower _Alignof(int) fixture with target alignment profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from _Alignof(int) fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn alignof_int_bytes() -> usize"),
        "{rust}"
    );
    assert!(rust.contains("return 4usize;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-alignof-int", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_alignof_size_t_without_desugared_alignment_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        pointer_width: 64,
        long_width: 64,
        ..TargetAbiProfile::default()
    };

    let error = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "alignof_size_t_bytes",
        Some(&target_abi),
    )
    .expect_err("_Alignof(size_t) must fail closed without desugared alignment profile");

    assert_eq!(error.kind, "unsupported_alignof_type");
    assert!(
        error.message.contains("_Alignof") && error.message.contains("alignment"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_alignof_size_t_with_desugared_alignment_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        pointer_width: 64,
        long_width: 64,
        long_align: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "alignof_size_t_bytes",
        Some(&target_abi),
    )
    .expect("lower _Alignof(size_t) fixture with clang-proven desugared alignment profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from _Alignof(size_t) fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn alignof_size_t_bytes() -> usize"),
        "{rust}"
    );
    assert!(rust.contains("return 8usize;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-alignof-size-t", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_sizeof_int_without_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "sizeof_int_bytes")
        .expect_err("sizeof result size_t must fail closed without target ABI profile");

    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error
            .message
            .contains("requires target ABI width provenance"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_binds_extended_target_abi_integer_widths() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    for (function, signature) in [
        ("identity_char", "pub fn identity_char(value: i8) -> i8"),
        ("identity_short", "pub fn identity_short(value: i16) -> i16"),
        (
            "identity_ushort",
            "pub fn identity_ushort(value: u16) -> u16",
        ),
        (
            "identity_long_long",
            "pub fn identity_long_long(value: i64) -> i64",
        ),
        (
            "identity_ulong_long",
            "pub fn identity_ulong_long(value: u64) -> u64",
        ),
    ] {
        let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
            &ast,
            function,
            Some(&target_abi),
        )
        .expect("lower extended target ABI fixture");
        let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect("emit Rust from extended target ABI fixture");

        assert!(emitted.rust.contains(signature), "{}", emitted.rust);
        assert!(emitted.rust.contains("return value;"), "{}", emitted.rust);
        assert_rust_snippet_compiles(function, &emitted.rust);
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_extended_target_abi_integer_widths_without_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");

    for function in [
        "identity_char",
        "identity_short",
        "identity_ushort",
        "identity_long_long",
        "identity_ulong_long",
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function)
            .expect_err("extended target ABI integers must fail closed without target profile");

        assert_eq!(error.kind, "unsupported_clang_type");
        assert!(
            error
                .message
                .contains("requires target ABI width provenance"),
            "{}",
            error.message
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_target_abi_ulong_identity_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/target_abi_ulong_identity_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "target_abi_ulong_identity",
        Some(&target_abi),
    )
    .expect("lower unsigned long fixture with target ABI profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from unsigned long fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn target_abi_ulong_identity(value: u64) -> u64"),
        "{rust}"
    );
    assert!(rust.contains("return value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-target-abi-ulong-identity", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_scalar_runtime_preconditions_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/scalar_runtime_preconditions_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "scalar_runtime_preconditions")
            .expect("lower committed clang AST scalar runtime preconditions fixture");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from scalar runtime preconditions fixture typed IR");
    let rust = &emitted.rust;

    assert!(lowered.globals.is_empty());
    assert!(rust.contains(
        "pub fn scalar_runtime_preconditions(value: i32, divisor: i32, count: i32) -> i32"
    ));
    assert!(
        rust.contains(".checked_add(1i32).expect(\"signed addition overflow\")"),
        "{rust}"
    );
    assert!(
        rust.contains(".checked_div(divisor).expect(\"division by zero or signed overflow\")"),
        "{rust}"
    );
    assert!(
        rust.contains(".checked_rem(5i32).expect(\"modulo by zero or signed overflow\")"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "checked_shl(core::convert::TryFrom::try_from(count).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\")"
        ),
        "{rust}"
    );
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-scalar-runtime-preconditions",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_scalar_div_rem_contract_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/scalar_div_rem_contract_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "scalar_div_rem_contract")
            .expect("lower committed clang AST scalar div/rem fixture");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from scalar div/rem fixture typed IR");
    let rust = &emitted.rust;

    assert!(lowered.globals.is_empty());
    assert!(rust.contains("pub fn scalar_div_rem_contract(value: i32) -> i32"));
    assert!(
        rust.contains(".checked_div(3i32).expect(\"division by zero or signed overflow\")"),
        "{rust}"
    );
    assert!(
        rust.contains(".checked_rem(5i32).expect(\"modulo by zero or signed overflow\")"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-scalar-div-rem-contract", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_while_countdown_positive_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/while_countdown_positive_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "while_countdown_positive")
            .expect("lower committed clang AST while countdown fixture");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from while countdown fixture typed IR");
    let rust = &emitted.rust;

    assert!(lowered.globals.is_empty());
    assert!(rust.contains("pub fn while_countdown_positive(mut value: i32) -> i32"));
    assert!(rust.contains("while (value > 0i32) {"), "{rust}");
    assert!(rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-while-countdown-positive", rust);
}

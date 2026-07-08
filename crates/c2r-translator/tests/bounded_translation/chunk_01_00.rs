#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_pointer_lvalue_to_rvalue_without_lowering_evidence() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("const int *", "const int *", ir_const(i32_ty.clone()), true);
    let lvalue_to_rvalue_expr: IrExpr = serde_json::from_value(serde_json::json!({
        "LValueToRValue": {
            "target": serde_json::to_value(&ptr_ty).unwrap(),
            "expr": serde_json::to_value(ir_var("values", ptr_ty.clone())).unwrap(),
            "source_span": null
        }
    }))
    .expect("deserialize explicit pointer lvalue-to-rvalue IR node");
    let ir = IrFunction {
        name: "bad_pointer_lvalue_read".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "values".to_string(),
            ty: ptr_ty,
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: lvalue_to_rvalue_expr,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("pointer lvalue-to-rvalue must stay fail closed");
    assert!(error.reason.contains("lvalue-to-rvalue target"));
    assert!(error.reason.contains("const int *"));
    assert!(error.reason.contains("unsupported"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_size_t_without_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "identity_size")
        .expect_err("size_t must fail closed without target ABI profile");

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
fn clang_ast_fixture_binds_size_t_with_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "identity_size",
        Some(&target_abi),
    )
    .expect("lower size_t fixture with target ABI profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from size_t fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn identity_size(value: usize) -> usize"),
        "{rust}"
    );
    assert!(rust.contains("return value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-target-abi-size-t", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_sizeof_int_with_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "sizeof_int_bytes",
        Some(&target_abi),
    )
    .expect("lower sizeof(int) fixture with target ABI profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from sizeof(int) fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn sizeof_int_bytes() -> usize"),
        "{rust}"
    );
    assert!(rust.contains("return 4usize;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-sizeof-int", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_sizeof_expression_with_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "sizeof_value_bytes",
        Some(&target_abi),
    )
    .expect("lower sizeof(value) fixture with target ABI profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from sizeof(value) fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn sizeof_value_bytes(value: i32) -> usize"),
        "{rust}"
    );
    assert!(rust.contains("return 4usize;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-sizeof-expression", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_sizeof_pointer_with_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "sizeof_const_int_ptr_bytes",
        Some(&target_abi),
    )
    .expect("lower sizeof(const int *) fixture with target ABI profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from sizeof(const int *) fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn sizeof_const_int_ptr_bytes() -> usize"),
        "{rust}"
    );
    assert!(rust.contains("return 8usize;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-sizeof-pointer", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_sizeof_int_array_with_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "small-int-test-abi".to_string(),
        endianness: Some("little".to_string()),
        int_width: 16,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 32,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "sizeof_int_array_bytes",
        Some(&target_abi),
    )
    .expect("lower sizeof(int[3]) fixture with target ABI profile");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from sizeof(int[3]) fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn sizeof_int_array_bytes() -> usize"),
        "{rust}"
    );
    assert!(rust.contains("return 6usize;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-sizeof-int-array", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_sizeof_int_array_without_target_abi_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
    ))
    .expect("fixture JSON");

    let error =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "sizeof_int_array_bytes")
            .expect_err("sizeof(int[3]) result size_t must fail closed without target ABI profile");

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
fn clang_ast_fixture_rejects_alignof_int_without_alignment_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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

    let error = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "alignof_int_bytes",
        Some(&target_abi),
    )
    .expect_err("_Alignof must fail closed without target alignment profile");

    assert_eq!(error.kind, "unsupported_alignof_type");
    assert!(
        error.message.contains("_Alignof") && error.message.contains("alignment"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_alignof_int_with_target_alignment_profile() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "../../fixtures/clang_ast/target_abi_width_ast.json"
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
        "../../fixtures/clang_ast/target_abi_ulong_identity_ast.json"
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
        "../../fixtures/clang_ast/scalar_runtime_preconditions_ast.json"
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
        "../../fixtures/clang_ast/scalar_div_rem_contract_ast.json"
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

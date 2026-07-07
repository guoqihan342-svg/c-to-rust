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
fn clang_ast_fixture_replays_scalar_fail_closed_refusal_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/scalar_runtime_preconditions_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "literal_divide_by_zero")
            .expect("lower committed clang AST scalar refusal fixture");
    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("literal division by zero from fixture must fail closed");

    assert!(error.reason.contains("division by zero literal"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_scalar_ub_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/scalar_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason) in [
        ("literal_modulo_by_zero", "modulo by zero literal"),
        ("shift_count_out_of_range", "shift count literal 32"),
        ("signed_right_shift_without_contract", "signed right shift"),
    ] {
        let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .unwrap_or_else(|error| {
                panic!("lower committed clang AST fixture {function_name}: {error}")
            });
        let error = match emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals) {
            Ok(emitted) => panic!(
                "fixture {function_name} must fail closed, emitted {}",
                emitted.rust
            ),
            Err(error) => error,
        };

        assert!(
            error.reason.contains(expected_reason),
            "expected {function_name} refusal to contain {expected_reason:?}, got {:?}",
            error.reason
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_array_decay_deref_of_local_fixed_array_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/array_decay_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "first_local_table")
        .expect("array decay through unary deref of local fixed array should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array decay through unary deref of local fixed array should emit");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_local_table() -> i32"), "{rust}");
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[0i32 as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-array-decay-deref-local-fixed-array",
        rust,
        r#"
    assert_eq!(first_local_table(), 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_allows_array_decay_inside_subscript_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/array_decay_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table")
        .expect("array decay in array subscript base should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array subscript base decay should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_local_table(i: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[i as usize];"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-array-decay-subscript", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_array_decay_pointer_add_deref_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/array_decay_pointer_add_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table_add")
            .expect("array decay through pointer-add deref of local fixed array should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array decay through pointer-add deref should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_local_table_add(i: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[i as usize];"), "{rust}");
    assert!(
        !rust.contains("return table[0i32 as usize];"),
        "pointer-add deref must not collapse to *table: {rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-array-decay-pointer-add-deref",
        rust,
        r#"
    assert_eq!(lookup_local_table_add(2), 3);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_array_to_pointer_decay_without_lowering_evidence() {
    let i32_ty = ir_i32();
    let array_ty = ir_array(i32_ty.clone(), 4);
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let decay_expr: IrExpr = serde_json::from_value(serde_json::json!({
        "ArrayToPointerDecay": {
            "target": serde_json::to_value(&pointer_ty).unwrap(),
            "expr": serde_json::to_value(ir_var("table", array_ty.clone())).unwrap(),
            "source_span": null
        }
    }))
    .expect("deserialize explicit array-to-pointer decay IR node");
    let ir = IrFunction {
        name: "bad_array_decay_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: array_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1", i32_ty.clone()),
                        ir_lit(2, "2", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                        ir_lit(4, "4", i32_ty.clone()),
                    ],
                    ty: array_ty,
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Expr {
                expr: decay_expr,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("array-to-pointer decay must stay fail closed");
    assert!(error.reason.contains("array-to-pointer decay"));
    assert!(error.reason.contains("explicit lowering evidence"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_array_decay_pointer_sub_deref_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/array_decay_pointer_add_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table_sub")
            .expect("array decay through pointer-sub deref should stay visible in typed IR");
    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("array decay through pointer-sub deref must stay fail-closed at emission");

    assert!(
        error.reason.contains("array-to-pointer decay")
            || error
                .reason
                .contains("deref expression requires readonly pointer evidence")
            || error.reason.contains("deref pointer must be Var"),
        "unexpected error: {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_sparse_designated_array_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "lookup_sparse_designated_table",
    )
    .expect("sparse designated fixed array initializer should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("sparse designated fixed array initializer should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_sparse_designated_table() -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [0i32, 7i32, 0i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[1i32 as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-sparse-designated-array-initializer",
        rust,
        r#"
    assert_eq!(lookup_sparse_designated_table(), 7);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_unexpanded_designated_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "reject_unexpanded_designated_table",
    )
    .expect_err("unexpanded DesignatedInitExpr must stay fail-closed");

    assert!(
        error.message.contains("DesignatedInitExpr"),
        "unexpected error: {error}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_sparse_designated_global_array_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/global_designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_global_sparse")
            .expect("sparse designated readonly global initializer should lower");
    assert_eq!(lowered.globals.len(), 1);
    assert_eq!(lowered.globals[0].name, "table");
    assert_eq!(
        lowered.globals[0].init,
        IrGlobalInit::IntegerArray(vec![0, 7, 0])
    );

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("sparse designated readonly global initializer should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("const TABLE: [i32; 3] = [0i32, 7i32, 0i32];"),
        "{rust}"
    );
    assert!(rust.contains("return TABLE[1i32 as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-sparse-designated-global-array-initializer",
        rust,
        r#"
    assert_eq!(lookup_global_sparse(), 7);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_referenced_unexpanded_global_designated_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/global_designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "reject_unexpanded_global_sparse",
    )
    .expect("function shape should lower before unsupported global dependency is emitted");
    assert!(
        lowered
            .globals
            .iter()
            .all(|global| global.name != "bad_table"),
        "unsupported bad_table global must not be collected"
    );

    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("referenced unexpanded global designated initializer must fail closed");
    assert!(
        error
            .reason
            .contains("index base bad_table is not declared"),
        "unexpected error: {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_readonly_mutable_restrict_noalias_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/restrict_pointer_params_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "copy_one_restrict")
        .expect("restrict-qualified pointer params should lower");
    let values_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "values")
        .expect("values param");
    let out_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "out")
        .expect("out param");
    assert!(values_param.ty.spelled.contains("restrict"));
    assert!(values_param.ty.canonical.contains("restrict"));
    assert!(out_param.ty.spelled.contains("restrict"));
    assert!(out_param.ty.canonical.contains("restrict"));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("restrict-qualified readonly input plus mutable output should emit");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(lowered.globals.is_empty());
    assert!(rust
        .contains("pub fn copy_one_restrict(i: i32, values: &[i32], mut out: &mut [i32]) -> i32"));
    assert!(rust.contains("out[i as usize] = values[i as usize];"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-clang-ast-restrict-pointer-copy-one", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_readonly_mutable_without_noalias_fails_closed() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/readonly_mutable_noalias_missing_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "copy_one")
        .expect("plain readonly input plus mutable output should lower before alias gate");
    let values_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "values")
        .expect("values param");
    let out_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "out")
        .expect("out param");
    assert!(!values_param.ty.spelled.contains("restrict"));
    assert!(!values_param.ty.canonical.contains("restrict"));
    assert!(!out_param.ty.spelled.contains("restrict"));
    assert!(!out_param.ty.canonical.contains("restrict"));

    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("plain readonly input plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
fn ir_integer(spelled: &str, canonical: &str, signed: bool, width: u16) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Integer { signed, width },
        is_const: false,
        width_bits: Some(width),
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_const(mut ty: IrType) -> IrType {
    ty.is_const = true;
    ty
}

#[cfg(feature = "typed-ir")]
fn ir_pointer(spelled: &str, canonical: &str, pointee: IrType, is_const: bool) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Pointer {
            pointee: Box::new(pointee),
        },
        is_const,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_u32() -> IrType {
    ir_integer("uint32_t", "unsigned int", false, 32)
}

#[cfg(feature = "typed-ir")]
fn ir_u8() -> IrType {
    ir_integer("uint8_t", "unsigned char", false, 8)
}

#[cfg(feature = "typed-ir")]
fn ir_usize() -> IrType {
    ir_integer("size_t", "unsigned long", false, 64)
}

#[cfg(feature = "typed-ir")]
fn ir_i32() -> IrType {
    ir_integer("int", "int", true, 32)
}

#[cfg(feature = "typed-ir")]
fn ir_void() -> IrType {
    IrType {
        spelled: "void".to_string(),
        canonical: "void".to_string(),
        kind: IrTypeKind::Void,
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_function_type(spelled: &str) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: spelled.to_string(),
        kind: IrTypeKind::Function,
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_record(name: &str) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: None,
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_record_with_fields(name: &str, fields: Vec<(&str, IrType)>) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: Some(
                fields
                    .into_iter()
                    .map(|(name, ty)| IrRecordField {
                        name: name.to_string(),
                        ty,
                    })
                    .collect(),
            ),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_var(name: &str, ty: IrType) -> IrExpr {
    IrExpr::Var {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_null_ptr(ty: IrType) -> IrExpr {
    IrExpr::NullPtr {
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_lit(value: u64, spelling: &str, ty: IrType) -> IrExpr {
    IrExpr::LitInt {
        value,
        spelling: spelling.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_array(element: IrType, len: usize) -> IrType {
    IrType {
        spelled: format!("{}[{len}]", element.spelled),
        canonical: format!("{}[{len}]", element.canonical),
        kind: IrTypeKind::Array {
            element: Box::new(element),
            len: Some(len),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn without_implicit_cast(expr: &IrExpr) -> &IrExpr {
    match expr {
        IrExpr::Cast {
            expr,
            implicit: true,
            ..
        } => without_implicit_cast(expr),
        _ => expr,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Binary {
        op,
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_conditional(condition: IrExpr, then_expr: IrExpr, else_expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Conditional {
        condition: Box::new(condition),
        then_expr: Box::new(then_expr),
        else_expr: Box::new(else_expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_deref(ptr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Deref {
        ptr: Box::new(ptr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_bitnot(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_neg(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Neg,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_not(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Not,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_control_flow_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/control_flow_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason, expected_range) in [
        (
            "label_refusal",
            "unsupported control-flow LabelStmt",
            "source_range=2:3-2:15",
        ),
        (
            "goto_refusal",
            "unsupported control-flow GotoStmt",
            "source_range=5:3-5:12",
        ),
        (
            "switch_refusal",
            "unsupported control-flow SwitchStmt",
            "source_range=8:3-8:48",
        ),
        (
            "case_refusal",
            "unsupported control-flow CaseStmt",
            "source_range=11:3-11:18",
        ),
        (
            "default_refusal",
            "unsupported control-flow DefaultStmt",
            "source_range=14:3-14:18",
        ),
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("control-flow fixture must fail closed during clang AST lowering");
        assert_eq!(error.kind, "unsupported_clang_stmt");
        assert!(
            error.message.contains(expected_reason),
            "expected {function_name} refusal to contain {expected_reason:?}, got {:?}",
            error.message
        );
        assert!(
            error
                .message
                .contains("requires structured CFG/relooper support"),
            "expected {function_name} refusal to mention CFG/relooper support, got {:?}",
            error.message
        );
        assert!(
            error.message.contains(expected_range),
            "expected {function_name} refusal to contain {expected_range:?}, got {:?}",
            error.message
        );
    }
}

#[cfg(feature = "typed-ir")]
fn flashdb_crc32_typed_ir() -> IrFunction {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        true,
    );
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        true,
    );

    let crc = || ir_var("crc", u32_ty.clone());
    let p = || ir_var("p", const_u8_ptr.clone());
    let size = || ir_var("size", usize_ty.clone());
    let crc32_table = || IrExpr::Var {
        name: "crc32_table".to_string(),
        ty: IrType {
            spelled: "const uint32_t[256]".to_string(),
            canonical: "const unsigned int[256]".to_string(),
            kind: IrTypeKind::Array {
                element: Box::new(u32_ty.clone()),
                len: Some(256),
            },
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        source_span: None,
    };

    let post_inc_p = IrExpr::IncDec {
        target: Box::new(p()),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty: const_u8_ptr.clone(),
        source_span: None,
    };
    let byte_read = IrExpr::Deref {
        ptr: Box::new(post_inc_p),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let promoted_byte = IrExpr::Cast {
        target: u32_ty.clone(),
        expr: Box::new(byte_read),
        implicit: true,
        source_span: None,
    };
    let table_index = ir_binary(
        IrBinOp::BitAnd,
        ir_binary(IrBinOp::BitXor, crc(), promoted_byte, u32_ty.clone()),
        ir_lit(0xFF, "0xFFU", u32_ty.clone()),
        u32_ty.clone(),
    );
    let table_lookup = IrExpr::Index {
        base: Box::new(crc32_table()),
        index: Box::new(table_index),
        ty: u32_ty.clone(),
        source_span: None,
    };
    let shift = ir_binary(
        IrBinOp::Shr,
        crc(),
        ir_lit(8, "8U", u32_ty.clone()),
        u32_ty.clone(),
    );

    IrFunction {
        name: "fdb_calc_crc32".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "buf".to_string(),
                ty: const_void_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "size".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: p(),
                value: IrExpr::Cast {
                    target: const_u8_ptr.clone(),
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Assign {
                target: crc(),
                value: ir_binary(
                    IrBinOp::BitXor,
                    crc(),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
                    u32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(size()),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: usize_ty,
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: crc(),
                    value: ir_binary(IrBinOp::BitXor, table_lookup, shift, u32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::BitXor,
                    crc(),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
                    u32_ty,
                )),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_u32_global_array(name: &str, len: usize, values: Vec<u64>) -> IrGlobal {
    let u32_ty = ir_u32();
    IrGlobal {
        name: name.to_string(),
        ty: IrType {
            spelled: format!("const uint32_t[{len}]"),
            canonical: format!("const unsigned int[{len}]"),
            kind: IrTypeKind::Array {
                element: Box::new(u32_ty),
                len: Some(len),
            },
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        init: if values.iter().all(|value| *value == 0) {
            IrGlobalInit::Zeroed
        } else {
            IrGlobalInit::IntegerArray(values)
        },
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn repeated_c_u32_initializer(len: usize, value: &str) -> String {
    std::iter::repeat_n(value, len)
        .collect::<Vec<_>>()
        .join(", ")
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_flashdb_crc32_without_readonly_global_table() {
    let error = emit_rust_from_ir(&flashdb_crc32_typed_ir())
        .expect_err("crc32 typed IR without a modeled readonly global table must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert!(!error.route.deprecated);
    assert!(error.reason.contains("crc32_table"));
    assert!(error.reason.contains("not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_flashdb_crc32_with_readonly_global_table_as_generic_route() {
    let global = ir_u32_global_array("crc32_table", 256, vec![0; 256]);
    let emitted = emit_rust_from_ir_with_globals(&flashdb_crc32_typed_ir(), &[global])
        .expect("emit flashdb crc32 through generic typed IR with global table");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32; 256];"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains(
        "crc = (CRC32_TABLE[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ crc.checked_shr(core::convert::TryFrom::try_from(8u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\"));"
    ));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-crc32-global-table-generic", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_global_array_initializer_length_mismatch() {
    let global = ir_u32_global_array("table", 4, vec![1, 2]);
    let ir = IrFunction {
        name: "return_zero".to_string(),
        return_type: ir_u32(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0U", ir_u32())),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir_with_globals(&ir, &[global])
        .expect_err("global initializer length mismatch must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("initializer length 2 does not match array length 4"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_value_field_read() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Member {
                base: Box::new(ir_var("p", point_ty)),
                field: "x".to_string(),
                ty: i32_ty,
                is_arrow: false,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record field read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("#[derive(Clone, Copy, Debug, Eq, PartialEq)]"));
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn point_x(p: Point) -> i32"));
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-record-value-field-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_value_field_assignment() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "set_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record field assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn set_point_x(mut p: Point, value: i32) -> i32"));
    assert!(rust.contains("p.x = value;"));
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-record-value-field-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_value_field_compound_assignment_shape() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let field_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: false,
        source_span: None,
    };
    let ir = IrFunction {
        name: "add_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: field_target.clone(),
                value: IrExpr::Binary {
                    op: IrBinOp::Add,
                    lhs: Box::new(field_target),
                    rhs: Box::new(ir_var("value", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record field compound shape");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn add_point_x(mut p: Point, value: i32) -> i32"));
    assert!(rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-record-value-field-compound-shape", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_copy_field_read() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "local_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", point_ty.clone())),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record local copy field read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn local_point_x(p: Point) -> i32"));
    assert!(rust.contains("let q: Point = p;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-copy-field-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_copy_with_equivalent_record_spelling() {
    let point_ty = ir_record("point");
    let mut const_point_ty = point_ty.clone();
    const_point_ty.spelled = "const struct point".to_string();
    const_point_ty.canonical = "struct point".to_string();
    const_point_ty.is_const = true;
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "local_const_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_point_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", const_point_ty)),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit record local copy despite non-semantic spelling differences");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn local_const_point_x(p: Point) -> i32"));
    assert!(rust.contains("let q: Point = p;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-copy-equivalent-spelling", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_copy_field_assignment() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "set_local_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", point_ty.clone())),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record local copy field assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub fn set_local_point_x(p: Point, value: i32) -> i32"));
    assert!(rust.contains("let mut q: Point = p;"));
    assert!(rust.contains("q.x = value;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-copy-field-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_assignment_value_copy() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "assign_local_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "r".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", point_ty.clone())),
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("q", point_ty.clone()),
                value: ir_var("r", point_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record local assignment copy");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub fn assign_local_point_x(p: Point, r: Point) -> i32"));
    assert!(rust.contains("let mut q: Point = p;"));
    assert!(rust.contains("q = r;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-assignment-value-copy", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_uninitialized_record_local_decl() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let ir = IrFunction {
        name: "bad_record_local".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("record locals need explicit initializer");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("decl q record initializer is required"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_uninitialized_record_local_address_when_field_is_read() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields("point", vec![("x", i32_ty.clone())]);
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_record_address_and_read".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "touch_point".to_string(),
                    args: vec![IrExpr::AddrOf {
                        operand: Box::new(ir_var("q", point_ty.clone())),
                        ty: point_ptr_ty,
                        source_span: None,
                    }],
                    ty: ir_void(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("address-taken record locals cannot also be read without an initializer");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("decl q record initializer is required"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_record_address_passed_to_direct_call() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let usize_ty = ir_usize();
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_with_local_blob".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "observe_blob".to_string(),
                    args: vec![IrExpr::AddrOf {
                        operand: Box::new(ir_var("blob", blob_ty)),
                        ty: blob_ptr_ty,
                        source_span: None,
                    }],
                    ty: i32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit address-of local record call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("let mut blob: FdbBlob = FdbBlob {"), "{rust}");
    assert!(rust.contains("buf: core::ptr::null_mut()"), "{rust}");
    assert!(rust.contains("size: 0usize"), "{rust}");
    assert!(rust.contains("return observe_blob(&mut blob);"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-local-record-address-call-arg",
        &format!(
            "fn observe_blob(blob: &mut FdbBlob) -> i32 {{ blob.size = 7usize; 7i32 }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_record_address_with_nested_record_zero_initializer() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let saved_ty = ir_record_with_fields(
        "fdb_blob_saved",
        vec![
            ("meta_addr", u32_ty.clone()),
            ("addr", u32_ty),
            ("len", usize_ty.clone()),
        ],
    );
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![
            ("buf", mut_void_ptr_ty.clone()),
            ("size", usize_ty),
            ("saved", saved_ty),
        ],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_with_nested_local_blob".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "observe_blob".to_string(),
                    args: vec![IrExpr::AddrOf {
                        operand: Box::new(ir_var("blob", blob_ty)),
                        ty: blob_ptr_ty,
                        source_span: None,
                    }],
                    ty: i32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit nested local record call arg");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct FdbBlobSaved"), "{rust}");
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("saved: FdbBlobSaved {"), "{rust}");
    assert!(rust.contains("meta_addr: 0u32"), "{rust}");
    assert!(rust.contains("addr: 0u32"), "{rust}");
    assert!(rust.contains("len: 0usize"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-local-record-address-nested-record",
        &format!(
            "fn observe_blob(blob: &mut FdbBlob) -> i32 {{ blob.saved.len = 7usize; 7i32 }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_discarded_pointer_return_call_with_opaque_void_arg() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let usize_ty = ir_usize();
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_blob_make".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: const_void_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "len".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "fdb_blob_make".to_string(),
                    args: vec![
                        IrExpr::AddrOf {
                            operand: Box::new(ir_var("blob", blob_ty)),
                            ty: blob_ptr_ty.clone(),
                            source_span: None,
                        },
                        ir_var("value", const_void_ptr_ty),
                        ir_var("len", usize_ty),
                    ],
                    ty: blob_ptr_ty,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit discarded pointer-return direct call statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn call_blob_make(value: *const core::ffi::c_void, len: usize) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let _ = fdb_blob_make(&mut blob, value, len);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-discarded-pointer-return-call-opaque-arg",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\n{rust}"
        ),
        "assert_eq!(call_blob_make(core::ptr::null(), 3usize), 0i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_blob_make_pointer_return_as_direct_call_argument() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_void_ptr_ty = ir_pointer("const void *", "void *", ir_const(ir_void()), false);
    let usize_ty = ir_usize();
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_kv_set_blob".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: const_void_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "len".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_kv_set_blob".to_string(),
                    args: vec![IrExpr::Call {
                        callee: "fdb_blob_make".to_string(),
                        args: vec![
                            IrExpr::AddrOf {
                                operand: Box::new(ir_var("blob", blob_ty)),
                                ty: blob_ptr_ty.clone(),
                                source_span: None,
                            },
                            ir_var("value", const_void_ptr_ty),
                            ir_var("len", usize_ty),
                        ],
                        ty: blob_ptr_ty,
                        source_span: None,
                    }],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit fdb_blob_make pointer return as direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("return fdb_kv_set_blob(fdb_blob_make(&mut blob, value, len));"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-blob-make-pointer-return-direct-call-arg",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\n{rust}"
        ),
        "assert_eq!(call_kv_set_blob(core::ptr::null(), 5usize), 5i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_blob_make_pointer_return_argument_with_strlen_leaf() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let usize_ty = ir_usize();
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_kv_set_blob_strlen".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_kv_set_blob".to_string(),
                    args: vec![IrExpr::Call {
                        callee: "fdb_blob_make".to_string(),
                        args: vec![
                            IrExpr::AddrOf {
                                operand: Box::new(ir_var("blob", blob_ty)),
                                ty: blob_ptr_ty.clone(),
                                source_span: None,
                            },
                            ir_var("value", const_u8_ptr_ty.clone()),
                            IrExpr::Call {
                                callee: "strlen".to_string(),
                                args: vec![ir_var("value", const_u8_ptr_ty)],
                                ty: usize_ty,
                                source_span: None,
                            },
                        ],
                        ty: blob_ptr_ty,
                        source_span: None,
                    }],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit fdb_blob_make strlen leaf as direct call arg");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn call_kv_set_blob_strlen(value: &[u8]) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(fdb_blob_make(&mut blob, value.as_ptr() as *const core::ffi::c_void, value.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-blob-make-pointer-return-strlen-leaf",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\n{rust}"
        ),
        "assert_eq!(call_kv_set_blob_strlen(b\"abc\\0\"), 3i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_external_direct_call_pointer_passthrough_with_blob_constructor_arg() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let const_u8_ptr_ty = ir_pointer(
        "const char *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let usize_ty = ir_usize();
    let kvdb_ty = ir_record("fdb_kvdb");
    let kvdb_ptr_ty = ir_pointer("fdb_kvdb_t", "struct fdb_kvdb *", kvdb_ty, false);
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![("buf", mut_void_ptr_ty.clone()), ("size", usize_ty.clone())],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "call_kv_set_blob_with_context".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "db".to_string(),
                ty: kvdb_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "key".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_kv_set_blob".to_string(),
                    args: vec![
                        ir_var("db", kvdb_ptr_ty),
                        ir_var("key", const_u8_ptr_ty.clone()),
                        IrExpr::Call {
                            callee: "fdb_blob_make".to_string(),
                            args: vec![
                                IrExpr::AddrOf {
                                    operand: Box::new(ir_var("blob", blob_ty)),
                                    ty: blob_ptr_ty.clone(),
                                    source_span: None,
                                },
                                ir_var("value", const_u8_ptr_ty.clone()),
                                IrExpr::Call {
                                    callee: "strlen".to_string(),
                                    args: vec![ir_var("value", const_u8_ptr_ty)],
                                    ty: usize_ty,
                                    source_span: None,
                                },
                            ],
                            ty: blob_ptr_ty,
                            source_span: None,
                        },
                    ],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit external direct call pointer passthrough compile-context candidate");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(
        rust.contains(
            "pub fn call_kv_set_blob_with_context(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: &[u8]) -> i32"
        ),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.as_ptr() as *const core::ffi::c_void, value.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-external-direct-call-pointer-passthrough-blob-constructor",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(_: *mut core::ffi::c_void, _: *const core::ffi::c_void, blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\n{rust}"
        ),
        "let mut db = 0u8; assert_eq!(call_kv_set_blob_with_context((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), b\"123\\0\"), 3i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_pointer_truthiness_blob_constructor_with_clang_size_t_strlen_leaf() {
    let mut_void_ptr_ty = ir_pointer("void *", "void *", ir_void(), false);
    let char_ty = ir_integer("const char", "char", true, 8);
    let const_char_ptr_ty = ir_pointer("const char *", "char *", ir_const(char_ty), false);
    let clang_size_t_ty = ir_integer("__size_t", "__size_t", false, 64);
    let kvdb_ty = ir_record("fdb_kvdb");
    let kvdb_ptr_ty = ir_pointer("fdb_kvdb_t", "struct fdb_kvdb *", kvdb_ty, false);
    let blob_ty = ir_record_with_fields(
        "fdb_blob",
        vec![
            ("buf", mut_void_ptr_ty.clone()),
            ("size", clang_size_t_ty.clone()),
        ],
    );
    let blob_ptr_ty = ir_pointer(
        "struct fdb_blob *",
        "struct fdb_blob *",
        blob_ty.clone(),
        false,
    );
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "set_or_delete".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "db".to_string(),
                ty: kvdb_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "key".to_string(),
                ty: const_char_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_char_ptr_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "blob".to_string(),
                ty: blob_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::If {
                condition: ir_var("value", const_char_ptr_ty.clone()),
                then_body: vec![IrStmt::Return {
                    value: Some(IrExpr::Call {
                        callee: "fdb_kv_set_blob".to_string(),
                        args: vec![
                            ir_var("db", kvdb_ptr_ty.clone()),
                            ir_var("key", const_char_ptr_ty.clone()),
                            IrExpr::Call {
                                callee: "fdb_blob_make".to_string(),
                                args: vec![
                                    IrExpr::AddrOf {
                                        operand: Box::new(ir_var("blob", blob_ty)),
                                        ty: blob_ptr_ty.clone(),
                                        source_span: None,
                                    },
                                    ir_var("value", const_char_ptr_ty.clone()),
                                    IrExpr::Call {
                                        callee: "strlen".to_string(),
                                        args: vec![ir_var("value", const_char_ptr_ty.clone())],
                                        ty: clang_size_t_ty,
                                        source_span: None,
                                    },
                                ],
                                ty: blob_ptr_ty,
                                source_span: None,
                            },
                        ],
                        ty: i32_ty.clone(),
                        source_span: None,
                    }),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fdb_kv_del".to_string(),
                    args: vec![ir_var("db", kvdb_ptr_ty), ir_var("key", const_char_ptr_ty)],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit pointer truthiness blob constructor with clang __size_t strlen leaf");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "pub fn set_or_delete(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: Option<&[i8]>) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("if value.is_some() {"), "{rust}");
    assert!(
        rust.contains(
            "return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.unwrap().as_ptr() as *const core::ffi::c_void, value.unwrap().iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")));"
        ),
        "{rust}"
    );
    assert!(rust.contains("return fdb_kv_del(db, key);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-pointer-truthiness-blob-constructor-clang-size-t",
        &format!(
            "fn fdb_blob_make(blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> *mut FdbBlob {{ blob.buf = value as *mut core::ffi::c_void; blob.size = len; blob as *mut FdbBlob }}\nfn fdb_kv_set_blob(_: *mut core::ffi::c_void, _: *const core::ffi::c_void, blob: *mut FdbBlob) -> i32 {{ unsafe {{ if blob.is_null() {{ -1i32 }} else {{ (*blob).size as i32 }} }} }}\nfn fdb_kv_del(_: *mut core::ffi::c_void, _: *const core::ffi::c_void) -> i32 {{ 7i32 }}\n{rust}"
        ),
        "let mut db = 0u8; assert_eq!(set_or_delete((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), Some(&[49i8, 50i8, 51i8, 0i8])), 3i32); assert_eq!(set_or_delete((&mut db as *mut u8).cast::<core::ffi::c_void>(), b\"boot\\0\".as_ptr().cast::<core::ffi::c_void>(), None), 7i32);",
    );
}

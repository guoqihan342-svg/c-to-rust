
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_real_fdb_kv_to_blob_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/real_fdb_kv_to_blob_ast.json"
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
        "fdb_kv_to_blob",
        Some(&target_abi),
    )
    .expect("lower real FlashDB fdb_kv_to_blob fixture without invoking clang");
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "kv".to_string(),
            mutable_param: "blob".to_string(),
        }],
        ..Default::default()
    };
    let emitted =
        emit_rust_from_ir_with_globals_and_policy(&lowered.function_ir, &lowered.globals, policy)
            .expect("emit Rust from real FlashDB fdb_kv_to_blob fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbKv"), "{rust}");
    assert!(rust.contains("pub struct FdbKvAddr"), "{rust}");
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("pub struct FdbBlobSaved"), "{rust}");
    assert!(
        rust.contains("pub fn fdb_kv_to_blob<'a>(kv: &FdbKv"),
        "{rust}"
    );
    assert!(rust.contains("blob: &'a mut FdbBlob"), "{rust}");
    assert!(
        rust.contains("blob.saved.meta_addr = kv.addr.start;"),
        "{rust}"
    );
    assert!(rust.contains("blob.saved.addr = kv.addr.value;"), "{rust}");
    assert!(rust.contains("blob.saved.len = kv.value_len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-real-fdb-kv-to-blob", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_usual_arithmetic_integral_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/usual_arithmetic_ast.json"
    ))
    .expect("fixture JSON");

    let add_byte = lower_function_and_globals_from_clang_ast_json_value(&ast, "add_byte")
        .expect("lower clang-proven usual arithmetic fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary { rhs, ty, .. }),
        ..
    }] = add_byte.function_ir.body.as_slice()
    else {
        panic!(
            "expected usual arithmetic return binary, got {:?}",
            add_byte.function_ir.body
        );
    };
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    assert!(
        matches!(
            rhs.as_ref(),
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ),
        "expected clang-proven IntegralCast on RHS, got {rhs:?}"
    );
    let emitted = emit_rust_from_ir_with_globals(&add_byte.function_ir, &add_byte.globals)
        .expect("emit Rust from clang-proven usual arithmetic fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn add_byte(acc: u32, byte: u8) -> u32"),
        "{rust}"
    );
    assert!(
        rust.contains("return acc.wrapping_add((byte as u32));"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-usual-arithmetic-cast", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_unary_plus_integer_promotion_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/unary_integer_conversion_ast.json"
    ))
    .expect("fixture JSON");

    let promoted = lower_function_and_globals_from_clang_ast_json_value(&ast, "promote_plus")
        .expect("lower clang-proven unary plus integer promotion fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Cast {
                implicit: true,
                target,
                expr,
                ..
            }),
        ..
    }] = promoted.function_ir.body.as_slice()
    else {
        panic!(
            "expected unary plus return to preserve IntegralPromotion as an IR cast, got {:?}",
            promoted.function_ir.body
        );
    };
    assert!(matches!(
        target.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let IrExpr::LValueToRValue {
        target: read_ty,
        expr: read_expr,
        ..
    } = expr.as_ref()
    else {
        panic!("expected promoted unary plus operand to preserve LValueToRValue, got {expr:?}");
    };
    assert!(matches!(
        read_ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 8
        }
    ));
    let IrExpr::Var { name, ty, .. } = read_expr.as_ref() else {
        panic!("expected promoted unary plus read operand to be the original parameter, got {read_expr:?}");
    };
    assert_eq!(name, "value");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 8
        }
    ));

    let emitted = emit_rust_from_ir_with_globals(&promoted.function_ir, &promoted.globals)
        .expect("emit Rust from clang-proven unary plus integer promotion fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn promote_plus(value: i8) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return (value as i32);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-unary-plus-integer-promotion",
        rust,
        "assert_eq!(promote_plus(-7i8), -7i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_integral_c_style_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/integral_c_style_cast_ast.json"
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

    let narrow = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "narrow",
        Some(&target_abi),
    )
    .expect("lower clang-proven integral C-style cast fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Cast {
                implicit,
                target,
                expr,
                ..
            }),
        ..
    }] = narrow.function_ir.body.as_slice()
    else {
        panic!(
            "expected integral C-style cast return to preserve an explicit IR cast, got {:?}",
            narrow.function_ir.body
        );
    };
    assert!(!implicit);
    assert!(matches!(
        target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    let IrExpr::LValueToRValue {
        target: read_ty,
        expr: read_expr,
        ..
    } = expr.as_ref()
    else {
        panic!("expected integral C-style cast operand to preserve LValueToRValue, got {expr:?}");
    };
    assert!(matches!(
        read_ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
    assert!(matches!(
        read_expr.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));

    let emitted = emit_rust_from_ir_with_globals(&narrow.function_ir, &narrow.globals)
        .expect("emit Rust from clang-proven integral C-style cast fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn narrow(value: u64) -> u32"),
        "{rust}"
    );
    assert!(rust.contains("return (value as u32);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-integral-c-style-cast",
        rust,
        "assert_eq!(narrow(0x1_0000_0001u64), 1u32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_integral_c_style_cast_without_target_abi() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/integral_c_style_cast_ast.json"
    ))
    .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "narrow")
        .expect_err("target-dependent C-style cast fixture must require target ABI");

    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error
            .message
            .contains("unsigned long requires target ABI width provenance"),
        "{error:?}"
    );
}

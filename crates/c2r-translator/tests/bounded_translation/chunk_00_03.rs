#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_implicit_integer_noop_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/implicit_integer_noop_cast_ast.json"
    ))
    .expect("fixture JSON");

    let identity = lower_function_and_globals_from_clang_ast_json_value(&ast, "identity_noop")
        .expect("lower clang-proven implicit integer NoOp cast fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Cast {
                implicit: true,
                target,
                expr,
                ..
            }),
        ..
    }] = identity.function_ir.body.as_slice()
    else {
        panic!(
            "expected integer NoOp return to preserve an IR cast, got {:?}",
            identity.function_ir.body
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
        target: read_target,
        expr: read_expr,
        ..
    } = expr.as_ref()
    else {
        panic!("expected NoOp cast operand to be an explicit LValueToRValue read, got {expr:?}");
    };
    assert!(matches!(
        read_target.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let IrExpr::Var { name, ty, .. } = read_expr.as_ref() else {
        panic!("expected LValueToRValue operand to be the original parameter, got {read_expr:?}");
    };
    assert_eq!(name, "value");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));

    let emitted = emit_rust_from_ir_with_globals(&identity.function_ir, &identity.globals)
        .expect("emit Rust from clang-proven implicit integer NoOp cast fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn identity_noop(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return (value as i32);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-implicit-integer-noop-cast",
        rust,
        "assert_eq!(identity_noop(-7i32), -7i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_integer_lvalue_to_rvalue_return_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/lvalue_to_rvalue_integer_return_ast.json"
    ))
    .expect("fixture JSON");

    let read_value = lower_function_and_globals_from_clang_ast_json_value(&ast, "read_value")
        .expect("lower clang-proven integer LValueToRValue fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(expr), ..
    }] = read_value.function_ir.body.as_slice()
    else {
        panic!(
            "expected integer LValueToRValue return expression, got {:?}",
            read_value.function_ir.body
        );
    };
    let lowered_json = serde_json::to_value(expr).expect("serialize return expression");
    let Some(lvalue_to_rvalue) = lowered_json.get("LValueToRValue") else {
        panic!("expected explicit LValueToRValue IR node, got {lowered_json}");
    };
    assert_eq!(lvalue_to_rvalue["target"]["kind"]["Integer"]["width"], 32);
    assert_eq!(lvalue_to_rvalue["expr"]["Var"]["name"], "value");

    let emitted = emit_rust_from_ir_with_globals(&read_value.function_ir, &read_value.globals)
        .expect("emit Rust from clang-proven integer LValueToRValue fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn read_value(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return value;"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-integer-lvalue-to-rvalue",
        rust,
        "assert_eq!(read_value(-7i32), -7i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_usual_arithmetic_missing_integral_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/usual_arithmetic_ast.json"
    ))
    .expect("fixture JSON");
    let missing_cast =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "missing_integral_cast")
            .expect("lower malformed fixture without explicit usual arithmetic cast");
    let error = emit_rust_from_ir_with_globals(&missing_cast.function_ir, &missing_cast.globals)
        .expect_err("missing usual arithmetic cast must fail closed");
    assert!(
        error.reason.contains(
            "usual arithmetic conversion requires explicit IntegralCast/IntegralPromotion"
        ),
        "{}",
        error.reason
    );
    assert!(
        error
            .reason
            .contains("binary operand types must match result type for +"),
        "{}",
        error.reason
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_explicit_enum_constant_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let status_code = lower_function_and_globals_from_clang_ast_json_value(&ast, "status_code")
        .expect("lower explicit enum constant fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::LitInt {
                value,
                spelling,
                ty,
                ..
            }),
        ..
    }] = status_code.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum constant return literal, got {:?}",
            status_code.function_ir.body
        );
    };
    assert_eq!(*value, 7);
    assert_eq!(spelling, "7");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&status_code.function_ir, &status_code.globals)
        .expect("emit Rust from explicit enum constant fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn status_code() -> i32"), "{rust}");
    assert!(rust.contains("return 7i32;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-constant", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_enum_constant_in_binary_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let add_status = lower_function_and_globals_from_clang_ast_json_value(&ast, "add_status")
        .expect("lower explicit enum constant binary fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary { rhs, ty, .. }),
        ..
    }] = add_status.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum constant binary return, got {:?}",
            add_status.function_ir.body
        );
    };
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt {
            value: 7,
            spelling,
            ..
        } if spelling == "7"
    ));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&add_status.function_ir, &add_status.globals)
        .expect("emit Rust from enum constant binary fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn add_status(value: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return value.checked_add(7i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-constant-binary", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_enum_constant_in_readonly_global_initializer_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_status_table")
        .expect("lower explicit enum constant global initializer fixture without invoking clang");
    assert_eq!(
        lowered
            .globals
            .iter()
            .find(|global| global.name == "status_table")
            .map(|global| &global.init),
        Some(&IrGlobalInit::IntegerArray(vec![7, 0]))
    );

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from enum constant global initializer fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("const STATUS_TABLE: [i32; 2] = [7i32, 0i32];"),
        "{rust}"
    );
    assert!(
        rust.contains("return STATUS_TABLE[0i32 as usize];"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-enum-constant-global-initializer",
        rust,
        r#"
    assert_eq!(lookup_status_table(), 7);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_implicit_enum_constant_in_readonly_global_initializer_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_pending_status_table")
            .expect("function shape should lower before unsupported enum global is emitted");
    assert!(
        lowered
            .globals
            .iter()
            .all(|global| global.name != "pending_status_table"),
        "implicit enum global initializer must not be collected"
    );

    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("referenced implicit enum global initializer must fail closed");
    assert!(
        error
            .reason
            .contains("index base pending_status_table is not declared"),
        "unexpected error: {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_enum_constant_without_explicit_value_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "implicit_status_code")
        .expect_err("implicit enum constant without explicit ConstantExpr must fail closed");
    assert_eq!(error.kind, "unsupported_clang_expr");
    assert!(
        error.message.contains("EnumConstantDecl STATUS_PENDING"),
        "{}",
        error.message
    );
    assert!(
        error.message.contains("explicit ConstantExpr value"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_keeps_enum_typed_function_unsupported_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
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
        "identity_status",
        Some(&target_abi),
    )
    .expect_err("enum-typed functions remain unsupported");
    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error.message.contains("EnumConstantDecl STATUS_PENDING"),
        "{}",
        error.message
    );
    assert!(
        error.message.contains("explicit ConstantExpr value"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_explicit_enum_typed_identity_without_target_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "identity_mode")
        .expect_err("enum-typed scalar lowering requires target ABI profile");
    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(error.message.contains("enum mode"), "{}", error.message);
    assert!(
        error.message.contains("target ABI profile evidence"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_named_enum_without_complete_definition_flag() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x3100",
                "kind": "EnumDecl",
                "name": "mode",
                "inner": [
                    {
                        "id": "0x3101",
                        "kind": "EnumConstantDecl",
                        "name": "MODE_OK",
                        "type": { "qualType": "int" },
                        "inner": [
                            {
                                "kind": "ConstantExpr",
                                "type": { "qualType": "int" },
                                "value": "0",
                                "inner": [
                                    {
                                        "kind": "IntegerLiteral",
                                        "type": { "qualType": "int" },
                                        "value": "0"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "identity_mode",
                "type": { "qualType": "enum mode (enum mode)" },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "value",
                        "type": { "qualType": "enum mode" }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "LValueToRValue",
                                        "type": { "qualType": "enum mode" },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "enum mode" },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "value"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    });
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
        "identity_mode",
        Some(&target_abi),
    )
    .expect_err("named enum without completeDefinition must fail closed");

    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error
            .message
            .contains("EnumDecl mode is not a complete definition"),
        "{}",
        error.message
    );
}

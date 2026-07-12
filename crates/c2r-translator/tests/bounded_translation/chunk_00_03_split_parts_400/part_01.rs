#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_implicit_enum_constant_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let status_code = lower_function_and_globals_from_clang_ast_json_value(&ast, "implicit_status_code")
        .expect("lower implicit enum constant fixture without invoking clang");
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
            "expected implicit enum constant return literal, got {:?}",
            status_code.function_ir.body
        );
    };
    assert_eq!(*value, 8);
    assert_eq!(spelling, "8");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&status_code.function_ir, &status_code.globals)
        .expect("emit Rust from implicit enum constant fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn implicit_status_code() -> i32"), "{rust}");
    assert!(rust.contains("return 8i32;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-implicit-enum-constant", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_enum_typed_function_with_target_abi_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../../fixtures/clang_ast/enum_constant_ast.json"))
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
        "identity_status",
        Some(&target_abi),
    )
    .expect("lower target-ABI-bound enum-typed function fixture without invoking clang");
    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lowered.function_ir.params.as_slice(),
        [IrParam {
            name,
            ty:
                IrType {
                    kind:
                        IrTypeKind::Integer {
                            signed: true,
                            width: 32
                        },
                    ..
                },
            ..
        }] if name == "value"
    ));
    let [IrStmt::Return {
        value: Some(IrExpr::Var { name, ty, .. }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum typed identity return variable, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(name, "value");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from target-ABI-bound enum typed fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn identity_status(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-typed-status", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_explicit_enum_typed_identity_without_target_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../../fixtures/clang_ast/enum_constant_ast.json"))
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

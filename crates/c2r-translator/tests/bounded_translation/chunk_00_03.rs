#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_anonymous_typedef_enum_alias_with_target_abi() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x2000",
                "kind": "EnumDecl",
                "completeDefinition": true,
                "inner": [
                    {
                        "id": "0x2001",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_NO_ERR",
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
                    },
                    {
                        "id": "0x2002",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_INIT_FAILED",
                        "type": { "qualType": "int" },
                        "inner": [
                            {
                                "kind": "ConstantExpr",
                                "type": { "qualType": "int" },
                                "value": "7",
                                "inner": [
                                    {
                                        "kind": "IntegerLiteral",
                                        "type": { "qualType": "int" },
                                        "value": "7"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": { "qualType": "enum fdb_err_t" },
                "inner": [
                    {
                        "kind": "EnumType",
                        "type": { "qualType": "enum fdb_err_t" },
                        "decl": {
                            "id": "0x2000",
                            "kind": "EnumDecl",
                            "name": ""
                        },
                        "isTagOwned": true
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "id_err",
                "type": {
                    "qualType": "fdb_err_t (fdb_err_t)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "e",
                        "type": {
                            "qualType": "fdb_err_t",
                            "desugaredQualType": "enum fdb_err_t"
                        }
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
                                        "type": {
                                            "qualType": "fdb_err_t",
                                            "desugaredQualType": "enum fdb_err_t"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t"
                                                },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "e"
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

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "id_err",
        Some(&target_abi),
    )
    .expect("lower anonymous typedef enum alias identity fixture without invoking clang");
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
        }] if name == "e"
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from anonymous typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-typedef-enum-alias", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_owned_typedef_enum_alias_without_complete_definition_flag() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x3000",
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": { "qualType": "enum fdb_err_t" },
                "inner": [
                    {
                        "id": "0x3001",
                        "kind": "EnumDecl",
                        "inner": [
                            {
                                "id": "0x3002",
                                "kind": "EnumConstantDecl",
                                "name": "FDB_NO_ERR",
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
                            },
                            {
                                "id": "0x3003",
                                "kind": "EnumConstantDecl",
                                "name": "FDB_INIT_FAILED",
                                "type": { "qualType": "int" },
                                "inner": [
                                    {
                                        "kind": "ConstantExpr",
                                        "type": { "qualType": "int" },
                                        "value": "7",
                                        "inner": [
                                            {
                                                "kind": "IntegerLiteral",
                                                "type": { "qualType": "int" },
                                                "value": "7"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "id_err",
                "type": {
                    "qualType": "fdb_err_t (fdb_err_t)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "e",
                        "type": {
                            "qualType": "fdb_err_t",
                            "desugaredQualType": "enum fdb_err_t",
                            "typeAliasDeclId": "0x3000"
                        }
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
                                        "type": {
                                            "qualType": "fdb_err_t",
                                            "desugaredQualType": "enum fdb_err_t",
                                            "typeAliasDeclId": "0x3000"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t",
                                                    "typeAliasDeclId": "0x3000"
                                                },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "e"
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

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "id_err",
        Some(&target_abi),
    )
    .expect("lower FlashDB-style owned typedef enum alias without completeDefinition flag");

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
        }] if name == "e"
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from FlashDB-style owned typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-owned-typedef-enum-alias", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_typedef_enum_alias_reference_with_implicit_values() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x3201",
                "kind": "EnumDecl",
                "inner": [
                    {
                        "id": "0x3202",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_NO_ERR",
                        "type": { "qualType": "int" }
                    },
                    {
                        "id": "0x3203",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_INIT_FAILED",
                        "type": { "qualType": "int" }
                    }
                ]
            },
            {
                "id": "0x3200",
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": { "qualType": "enum fdb_err_t" },
                "inner": [
                    {
                        "kind": "EnumType",
                        "type": { "qualType": "enum fdb_err_t" },
                        "decl": {
                            "kind": "EnumDecl",
                            "id": "0x3201"
                        }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "id_err",
                "type": {
                    "qualType": "fdb_err_t (fdb_err_t)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "e",
                        "type": {
                            "qualType": "fdb_err_t",
                            "desugaredQualType": "enum fdb_err_t",
                            "typeAliasDeclId": "0x3200"
                        }
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
                                        "type": {
                                            "qualType": "fdb_err_t",
                                            "desugaredQualType": "enum fdb_err_t",
                                            "typeAliasDeclId": "0x3200"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t",
                                                    "typeAliasDeclId": "0x3200"
                                                },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "e"
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

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "id_err",
        Some(&target_abi),
    )
    .expect("lower FlashDB-style typedef enum alias reference with implicit values");

    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from FlashDB-style implicit typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-typedef-enum-alias-implicit-values",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_enum_local_variable_branch_and_assignment_with_target_abi() {
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

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "choose_mode",
        Some(&target_abi),
    )
    .expect("lower explicit i32 enum local variable fixture without invoking clang");
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
    let [IrStmt::Decl {
        name: decl_name,
        ty: decl_ty,
        init: Some(IrExpr::LitInt { value: 1, .. }),
        ..
    }, IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum local declaration, branch assignment, and return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(decl_name, "current");
    assert!(matches!(
        decl_ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::Eq,
            lhs,
            rhs,
            ..
        } if matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "value")
            && matches!(rhs.as_ref(), IrExpr::LitInt { value: 2, .. })
    ));
    assert!(else_body.is_empty());
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign {
            target: IrExpr::Var { name: target_name, .. },
            value: IrExpr::LitInt { value: 2, .. },
            ..
        }] if target_name == "current"
    ));
    assert_eq!(return_name, "current");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from explicit i32 enum local variable fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn choose_mode(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let mut current: i32 = 1i32;"), "{rust}");
    assert!(rust.contains("if (value == 2i32)"), "{rust}");
    assert!(rust.contains("current = 2i32;"), "{rust}");
    assert!(rust.contains("return current;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-local-variable", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_sizeof_enum_without_layout_abi() {
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
        "sizeof_mode_bytes",
        Some(&target_abi),
    )
    .expect_err("sizeof(enum) still needs explicit enum layout/ABI proof");
    assert_eq!(error.kind, "unsupported_sizeof_type");
    assert!(
        error.message.contains("sizeof(enum mode)"),
        "{}",
        error.message
    );
    assert!(
        error
            .message
            .contains("requires explicit C layout/ABI provenance"),
        "{}",
        error.message
    );
}

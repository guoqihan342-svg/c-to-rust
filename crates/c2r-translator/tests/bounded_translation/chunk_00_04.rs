#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_explicit_i32_enum_typed_identity_with_target_abi() {
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
        "identity_mode",
        Some(&target_abi),
    )
    .expect("lower explicit i32 enum-typed identity fixture without invoking clang");
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
        .expect("emit Rust from explicit i32 enum-typed identity fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn identity_mode(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-typed-identity", rust);
}
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
fn clang_ast_fixture_lowers_elaborated_typedef_enum_alias_with_target_abi() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x4000",
                "kind": "EnumDecl",
                "inner": [
                    {
                        "id": "0x4001",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_NO_ERR",
                        "type": { "qualType": "int" }
                    },
                    {
                        "id": "0x4002",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_INIT_FAILED",
                        "type": { "qualType": "int" }
                    }
                ]
            },
            {
                "id": "0x4003",
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": {
                    "qualType": "enum fdb_err_t",
                    "desugaredQualType": "fdb_err_t"
                },
                "inner": [
                    {
                        "id": "0x4004",
                        "kind": "ElaboratedType",
                        "type": { "qualType": "enum fdb_err_t" },
                        "ownedTagDecl": {
                            "id": "0x4000",
                            "kind": "EnumDecl",
                            "name": ""
                        },
                        "inner": [
                            {
                                "id": "0x4005",
                                "kind": "EnumType",
                                "type": { "qualType": "fdb_err_t" },
                                "decl": {
                                    "id": "0x4000",
                                    "kind": "EnumDecl",
                                    "name": ""
                                }
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
                            "typeAliasDeclId": "0x4003"
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
                                            "typeAliasDeclId": "0x4003"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t",
                                                    "typeAliasDeclId": "0x4003"
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
    .expect("lower FlashDB-style elaborated typedef enum alias");

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
        .expect("emit Rust from FlashDB-style elaborated typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-elaborated-typedef-enum-alias",
        rust,
    );
}

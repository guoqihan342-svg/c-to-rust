#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_local_fixed_array_index_compound_assignment() {
    let u8_ty = ClangTypeSkeleton {
        spelled: "unsigned char".to_string(),
        canonical: "unsigned char".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let array_ty = ClangTypeSkeleton {
        spelled: "unsigned char[2]".to_string(),
        canonical: "unsigned char[2]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(u8_ty.clone()),
            len: Some(2),
        },
    };
    let local_var = || ClangExprSkeleton::DeclRef {
        name: "local".to_string(),
        ty: array_ty.clone(),
    };
    let slot = || ClangExprSkeleton::Index {
        base: Box::new(local_var()),
        index: Box::new(ClangExprSkeleton::IntegerLiteral {
            value: 1,
            spelling: "1".to_string(),
            ty: int_ty.clone(),
        }),
        ty: u8_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "update_local_slot".to_string(),
        return_type: u8_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "bits".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "local".to_string(),
                ty: array_ty.clone(),
                init: Some(ClangExprSkeleton::ArrayLiteral {
                    elements: vec![
                        ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1".to_string(),
                            ty: u8_ty.clone(),
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 2,
                            spelling: "2".to_string(),
                            ty: u8_ty.clone(),
                        },
                    ],
                    ty: array_ty.clone(),
                }),
            },
            ClangStmtSkeleton::CompoundAssign {
                target: slot(),
                op: ClangBinaryOperator::BitOr,
                value: ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::BitAnd,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "bits".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                        value: 15,
                        spelling: "15".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                },
                result_ty: u8_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::Return {
                value: Some(slot()),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton)
        .expect("local fixed array index compound assignment should lower");
    let [IrStmt::Decl { .. }, IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] =
        ir.body.as_slice()
    else {
        panic!("expected local array declaration, assignment, and return");
    };
    assert!(matches!(target, IrExpr::Index { .. }));
    assert!(matches!(
        value,
        IrExpr::Cast {
            expr,
            target,
            implicit: true,
            ..
        } if matches!(&target.kind, IrTypeKind::Integer { signed: false, width: 8 })
            && matches!(expr.as_ref(), IrExpr::Binary { op: IrBinOp::BitOr, .. })
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit local fixed array index compound assignment");
    assert!(rust.contains("let mut local: [u8; 2] = [1u8, 2u8];"));
    assert!(rust.contains("local[1i32 as usize] ="));
    assert!(rust.contains("| (bits & 15i32)"));
    assert_rust_snippet_runs(
        "typed-ir-local-fixed-array-index-compound-assignment",
        &rust,
        r#"
    assert_eq!(update_local_slot(4), 6u8);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_rejects_index_compound_assignment_call_rhs_without_clang() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "FunctionDecl",
            "name": "reject_effectful_rhs",
            "type": { "qualType": "int (int *, int)" },
            "inner": [
                {
                    "kind": "ParmVarDecl",
                    "name": "table",
                    "type": { "qualType": "int *" }
                },
                {
                    "kind": "ParmVarDecl",
                    "name": "position",
                    "type": { "qualType": "int" }
                },
                {
                    "kind": "CompoundStmt",
                    "inner": [
                        {
                            "kind": "CompoundAssignOperator",
                            "opcode": "+=",
                            "type": { "qualType": "int" },
                            "computeLHSType": { "qualType": "int" },
                            "computeResultType": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "ArraySubscriptExpr",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "ImplicitCastExpr",
                                            "castKind": "LValueToRValue",
                                            "type": { "qualType": "int *" },
                                            "inner": [{
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "int *" },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "table"
                                                }
                                            }]
                                        },
                                        {
                                            "kind": "ImplicitCastExpr",
                                            "castKind": "LValueToRValue",
                                            "type": { "qualType": "int" },
                                            "inner": [{
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "int" },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "position"
                                                }
                                            }]
                                        }
                                    ]
                                },
                                {
                                    "kind": "CallExpr",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "ImplicitCastExpr",
                                            "castKind": "FunctionToPointerDecay",
                                            "type": { "qualType": "int (*)(int *)" },
                                            "inner": [{
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "int (int *)" },
                                                "referencedDecl": {
                                                    "kind": "FunctionDecl",
                                                    "name": "mutate"
                                                }
                                            }]
                                        },
                                        {
                                            "kind": "UnaryOperator",
                                            "opcode": "&",
                                            "type": { "qualType": "int *" },
                                            "inner": [{
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "int" },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "position"
                                                }
                                            }]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            "kind": "ReturnStmt",
                            "inner": [{
                                "kind": "IntegerLiteral",
                                "type": { "qualType": "int" },
                                "value": "0"
                            }]
                        }
                    ]
                }
            ]
        }]
    });

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "reject_effectful_rhs")
        .expect_err("call RHS may mutate the index and must fail closed");

    assert_eq!(error.kind, "unsupported_clang_stmt");
    assert!(error
        .message
        .contains("index compound assignment RHS must be built from integer literals"));
}

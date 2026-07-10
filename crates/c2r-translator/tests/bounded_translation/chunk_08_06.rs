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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_index_compound_assignment_base_boundaries() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let const_int_ty = ClangTypeSkeleton {
        spelled: "const int".to_string(),
        canonical: "int".to_string(),
        kind: int_ty.kind.clone(),
    };
    let int_ptr_ty = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(int_ty.clone()),
            width: None,
        },
    };
    let cases = vec![
        (
            "const_pointer",
            ClangTypeSkeleton {
                spelled: "const int *".to_string(),
                canonical: "const int *".to_string(),
                kind: ClangTypeKind::Pointer {
                    pointee: Box::new(const_int_ty),
                    width: None,
                },
            },
            "mutable integer element type",
        ),
        (
            "pointer_element",
            ClangTypeSkeleton {
                spelled: "int **".to_string(),
                canonical: "int **".to_string(),
                kind: ClangTypeKind::Pointer {
                    pointee: Box::new(int_ptr_ty),
                    width: None,
                },
            },
            "integer element type",
        ),
        (
            "incomplete_array",
            ClangTypeSkeleton {
                spelled: "int[]".to_string(),
                canonical: "int[]".to_string(),
                kind: ClangTypeKind::Array {
                    element: Box::new(int_ty.clone()),
                    len: None,
                },
            },
            "complete fixed length",
        ),
    ];

    for (case, base_ty, expected) in cases {
        let skeleton = ClangFunctionSkeleton {
            name: format!("reject_{case}"),
            return_type: int_ty.clone(),
            params: vec![ClangParamSkeleton {
                name: "table".to_string(),
                ty: base_ty.clone(),
            }],
            body: vec![ClangStmtSkeleton::CompoundAssign {
                target: ClangExprSkeleton::Index {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "table".to_string(),
                        ty: base_ty,
                    }),
                    index: Box::new(ClangExprSkeleton::IntegerLiteral {
                        value: 0,
                        spelling: "0".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                },
                op: ClangBinaryOperator::BitOr,
                value: ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            }],
        };

        let error = lower_function_skeleton(&skeleton)
            .expect_err("unsupported index compound assignment base must fail closed");
        assert_eq!(error.kind, "unsupported_compound_assignment_target");
        assert!(
            error.message.contains(expected),
            "case {case}: unexpected error {}",
            error.message
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_effectful_index_compound_assignment_indices() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let int_ptr_ty = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(int_ty.clone()),
            width: None,
        },
    };
    let record_ty = ClangTypeSkeleton {
        spelled: "struct cursor".to_string(),
        canonical: "struct cursor".to_string(),
        kind: ClangTypeKind::Record {
            name: "cursor".to_string(),
        },
    };
    let index_var = || ClangExprSkeleton::DeclRef {
        name: "position".to_string(),
        ty: int_ty.clone(),
    };
    let cases = vec![
        (
            "call",
            ClangExprSkeleton::Call {
                callee: "next_position".to_string(),
                args: vec![],
                ty: int_ty.clone(),
            },
        ),
        (
            "incdec",
            ClangExprSkeleton::IncDec {
                target: Box::new(index_var()),
                op: ClangIncDecOperator::Inc,
                prefix: false,
                ty: int_ty.clone(),
            },
        ),
        (
            "deref",
            ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::DeclRef {
                    name: "cursor_ptr".to_string(),
                    ty: int_ptr_ty.clone(),
                }),
                ty: int_ty.clone(),
            },
        ),
        (
            "member",
            ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "cursor".to_string(),
                    ty: record_ty,
                }),
                field: "position".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
        ),
    ];

    for (case, index) in cases {
        let skeleton = ClangFunctionSkeleton {
            name: format!("reject_{case}_index"),
            return_type: int_ty.clone(),
            params: vec![
                ClangParamSkeleton {
                    name: "table".to_string(),
                    ty: int_ptr_ty.clone(),
                },
                ClangParamSkeleton {
                    name: "position".to_string(),
                    ty: int_ty.clone(),
                },
            ],
            body: vec![ClangStmtSkeleton::CompoundAssign {
                target: ClangExprSkeleton::Index {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "table".to_string(),
                        ty: int_ptr_ty.clone(),
                    }),
                    index: Box::new(index),
                    ty: int_ty.clone(),
                },
                op: ClangBinaryOperator::BitAnd,
                value: ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            }],
        };

        let error = lower_function_skeleton(&skeleton)
            .expect_err("effectful index compound assignment index must fail closed");
        assert_eq!(error.kind, "unsupported_compound_assignment_target");
        assert!(
            error.message.contains("side-effect-free integer literal"),
            "case {case}: unexpected error {}",
            error.message
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_integer_conditional_return_value() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "pick".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "flag".to_string(),
                ty: int_ty.clone(),
            },
            ClangParamSkeleton {
                name: "left".to_string(),
                ty: int_ty.clone(),
            },
            ClangParamSkeleton {
                name: "right".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Conditional {
                condition: Box::new(ClangExprSkeleton::DeclRef {
                    name: "flag".to_string(),
                    ty: int_ty.clone(),
                }),
                then_expr: Box::new(ClangExprSkeleton::DeclRef {
                    name: "left".to_string(),
                    ty: int_ty.clone(),
                }),
                else_expr: Box::new(ClangExprSkeleton::DeclRef {
                    name: "right".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty.clone(),
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower conditional return skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Conditional {
                condition,
                then_expr,
                else_expr,
                ty,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected conditional return, got {:?}", ir.body);
    };
    assert!(matches!(condition.as_ref(), IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(then_expr.as_ref(), IrExpr::Var { name, .. } if name == "left"));
    assert!(matches!(else_expr.as_ref(), IrExpr::Var { name, .. } if name == "right"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit conditional return from lowered skeleton");
    assert!(rust.contains("pub fn pick(flag: i32, left: i32, right: i32) -> i32"));
    assert!(rust.contains("return (if flag != 0i32 { left } else { right });"));
    assert_rust_snippet_compiles("typed-ir-clang-conditional-return", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_compound_assignment_non_var_target() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let int_ptr_ty = ClangTypeSkeleton {
        spelled: "int *".to_string(),
        canonical: "int *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(int_ty.clone()),
            width: None,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_compound_target".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: int_ptr_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: int_ptr_ty,
                }),
                ty: int_ty.clone(),
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("compound assignment must reject non-var targets");

    assert_eq!(error.kind, "unsupported_compound_assignment_target");
    assert!(error
        .message
        .contains("compound assignment target must be a simple variable"));
}

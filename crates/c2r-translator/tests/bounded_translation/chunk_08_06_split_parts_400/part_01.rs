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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn clang_scalar_if_skeleton() -> ClangFunctionSkeleton {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    ClangFunctionSkeleton {
        name: "adjust_if".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
            ClangParamSkeleton {
                name: "flag".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::DeclRef {
                    name: "flag".to_string(),
                    ty: int_ty.clone(),
                },
                then_body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "value".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
                else_body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "value".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::Unary {
                            op: ClangUnaryOperator::BitNot,
                            operand: Box::new(ClangExprSkeleton::IntegerLiteral {
                                value: 0,
                                spelling: "0".to_string(),
                                ty: int_ty.clone(),
                            }),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    }
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_simple_if_statement() {
    let skeleton = clang_scalar_if_skeleton();

    let ir = lower_function_skeleton(&skeleton).expect("lower if statement");

    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", ir.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_if_without_else_to_empty_else_body() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "adjust_if_no_else".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
            ClangParamSkeleton {
                name: "flag".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::DeclRef {
                    name: "flag".to_string(),
                    ty: int_ty.clone(),
                },
                then_body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "value".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
                else_body: vec![],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower if without else");

    let [IrStmt::If { else_body, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected if followed by return, got {:?}", ir.body);
    };
    assert!(
        else_body.is_empty(),
        "expected missing else to lower to empty else body"
    );
}

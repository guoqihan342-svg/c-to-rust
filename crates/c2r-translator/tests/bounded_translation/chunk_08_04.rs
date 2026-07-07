#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_short_circuit_if_condition() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "short_circuit".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "left".to_string(),
                ty: int_ty.clone(),
            },
            ClangParamSkeleton {
                name: "right".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::LogAnd,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "left".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "right".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                },
                then_body: vec![ClangStmtSkeleton::Return {
                    value: Some(ClangExprSkeleton::IntegerLiteral {
                        value: 1,
                        spelling: "1".to_string(),
                        ty: int_ty.clone(),
                    }),
                }],
                else_body: vec![],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty.clone(),
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower short-circuit if condition");

    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::LogAnd,
            ..
        },
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!(
            "expected short-circuit if followed by return, got {:?}",
            ir.body
        );
    };

    let rust = emit_rust_from_ir(&ir).expect("emit short-circuit if from lowered IR");
    assert!(rust.contains("pub fn short_circuit(left: i32, right: i32) -> i32"));
    assert!(rust.contains("if (left != 0i32 && right != 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-clang-if-short-circuit", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_logical_not_if_condition() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "is_zero".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::Unary {
                    op: ClangUnaryOperator::Not,
                    operand: Box::new(ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                },
                then_body: vec![ClangStmtSkeleton::Return {
                    value: Some(ClangExprSkeleton::IntegerLiteral {
                        value: 1,
                        spelling: "1".to_string(),
                        ty: int_ty.clone(),
                    }),
                }],
                else_body: vec![],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower logical not if condition");

    let [IrStmt::If {
        condition: IrExpr::Unary {
            op: IrUnOp::Not, ..
        },
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!(
            "expected logical not if followed by return, got {:?}",
            ir.body
        );
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not if from lowered IR");
    assert!(rust.contains("if value == 0i32 {"));
    assert_rust_snippet_compiles("typed-ir-clang-if-logical-not", &rust);
}

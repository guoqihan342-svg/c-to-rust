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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_comparison_if_condition() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "adjust_positive".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Gt,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                        value: 0,
                        spelling: "0".to_string(),
                        ty: int_ty.clone(),
                    }),
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
    let ir = lower_function_skeleton(&skeleton).expect("lower comparison if condition");

    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::Gt, ..
        },
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!(
            "expected comparison if followed by return, got {:?}",
            ir.body
        );
    };

    let rust = emit_rust_from_ir(&ir).expect("emit comparison if from lowered IR");
    assert!(rust.contains("if (value > 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-clang-if-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_typed_ir_for_loop() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "sum_to_limit".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "limit".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "total".to_string(),
                ty: int_ty.clone(),
                init: Some(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty.clone(),
                }),
            },
            ClangStmtSkeleton::For {
                init: vec![ClangStmtSkeleton::Decl {
                    name: "i".to_string(),
                    ty: int_ty.clone(),
                    init: Some(ClangExprSkeleton::IntegerLiteral {
                        value: 0,
                        spelling: "0".to_string(),
                        ty: int_ty.clone(),
                    }),
                }],
                condition: Some(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Lt,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "i".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "limit".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                }),
                step: Some(Box::new(ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "i".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "i".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                })),
                body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "total".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "total".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "i".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "total".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower typed IR for loop");

    let [IrStmt::Decl { name, .. }, IrStmt::For {
        init, step, body, ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", ir.body);
    };
    assert_eq!(name, "total");
    assert!(matches!(init.as_slice(), [IrStmt::Decl { name, .. }] if name == "i"));
    assert!(matches!(step.as_deref(), Some(IrStmt::Assign { .. })));
    assert!(matches!(body.as_slice(), [IrStmt::Assign { .. }]));

    let rust = emit_rust_from_ir(&ir).expect("emit typed IR for loop from skeleton");
    assert!(rust.contains("pub fn sum_to_limit(limit: i32) -> i32"));
    assert!(rust.contains("{\n        let mut i: i32 = 0i32;\n        while (i < limit) {"));
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\");"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-clang-for-skeleton", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_comparison_return_value() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "positive_as_int".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Gt,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower comparison return value");

    let [IrStmt::Return {
        value: Some(IrExpr::Binary {
            op: IrBinOp::Gt, ..
        }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected comparison return, got {:?}", ir.body);
    };

    let rust = emit_rust_from_ir(&ir).expect("emit comparison return from lowered IR");
    assert!(rust.contains("return (if (value > 0i32) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-clang-return-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_comparison_decl_initializer() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "cmp_init".to_string(),
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
            ClangStmtSkeleton::Decl {
                name: "out".to_string(),
                ty: int_ty.clone(),
                init: Some(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Eq,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "left".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "right".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "out".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower comparison decl initializer");

    let [IrStmt::Decl {
        init: Some(IrExpr::Binary {
            op: IrBinOp::Eq, ..
        }),
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!(
            "expected comparison decl initializer followed by return, got {:?}",
            ir.body
        );
    };

    let rust = emit_rust_from_ir(&ir).expect("emit comparison decl initializer from lowered IR");
    assert!(rust.contains("let mut out: i32 = (if (left == right) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-clang-decl-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_comparison_assignment_value() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "cmp_assign".to_string(),
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
            ClangStmtSkeleton::Assign {
                target: ClangExprSkeleton::DeclRef {
                    name: "left".to_string(),
                    ty: int_ty.clone(),
                },
                value: ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Neq,
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
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "left".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower comparison assignment value");

    let [IrStmt::Assign {
        value: IrExpr::Binary {
            op: IrBinOp::Neq, ..
        },
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!(
            "expected comparison assignment followed by return, got {:?}",
            ir.body
        );
    };

    let rust = emit_rust_from_ir(&ir).expect("emit comparison assignment from lowered IR");
    assert!(rust.contains("pub fn cmp_assign(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains("left = (if (left != right) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-clang-assign-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_short_circuit_value_positions() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "short_circuit_values".to_string(),
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
            ClangStmtSkeleton::Decl {
                name: "out".to_string(),
                ty: int_ty.clone(),
                init: Some(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::LogOr,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "left".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "right".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Assign {
                target: ClangExprSkeleton::DeclRef {
                    name: "left".to_string(),
                    ty: int_ty.clone(),
                },
                value: ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::LogAnd,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "left".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Gt,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "right".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 0,
                            spelling: "0".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                },
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::LogOr,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "left".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "out".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower short-circuit value positions");

    let [IrStmt::Decl {
        init: Some(IrExpr::Binary {
            op: IrBinOp::LogOr, ..
        }),
        ..
    }, IrStmt::Assign {
        value: IrExpr::Binary {
            op: IrBinOp::LogAnd,
            ..
        },
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Binary {
            op: IrBinOp::LogOr, ..
        }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!(
            "expected short-circuit decl, assignment, and return values, got {:?}",
            ir.body
        );
    };

    let rust = emit_rust_from_ir(&ir).expect("emit short-circuit values from lowered IR");
    assert!(rust.contains("pub fn short_circuit_values(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains(
        "let mut out: i32 = (if (left != 0i32 || right != 0i32) { 1i32 } else { 0i32 });"
    ));
    assert!(rust.contains("left = (if (left != 0i32 && (right > 0i32)) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return (if (left != 0i32 || out != 0i32) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-clang-short-circuit-values", &rust);
}

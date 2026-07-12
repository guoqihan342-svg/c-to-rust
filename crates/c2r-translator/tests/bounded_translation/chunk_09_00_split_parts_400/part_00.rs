#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_logical_not_return_value() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "is_zero_value".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Unary {
                op: ClangUnaryOperator::Not,
                operand: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower logical not return value");

    let [IrStmt::Return {
        value: Some(IrExpr::Unary {
            op: IrUnOp::Not, ..
        }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected logical not return, got {:?}", ir.body);
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not return from lowered IR");
    assert!(rust.contains("return (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-clang-return-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_emits_postfix_increment_value_decl_initializer() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "postfix_inc_value_decl".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "out".to_string(),
                ty: int_ty.clone(),
                init: Some(ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Inc,
                    prefix: false,
                    ty: int_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Add,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "out".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower postfix increment value decl");
    let rust = emit_rust_from_ir(&ir).expect("emit postfix increment value decl");

    assert!(rust.contains("pub fn postfix_inc_value_decl(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = post_inc_value;"));
    assert_rust_snippet_runs(
        "typed-ir-clang-postfix-inc-value-decl",
        &rust,
        "    assert_eq!(postfix_inc_value_decl(5), 11);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_if_from_clang_lowered_ir() {
    let skeleton = clang_scalar_if_skeleton();
    let ir = lower_function_skeleton(&skeleton).expect("lower scalar if skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if from lowered IR");

    assert!(rust.contains("pub fn adjust_if(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-scalar-if", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_postfix_decrement_condition() {
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while_size".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "size".to_string(),
                ty: size_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "size".to_string(),
                        ty: size_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Dec,
                    prefix: false,
                    ty: size_ty.clone(),
                },
                body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                    value: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower postfix decrement condition");

    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", ir.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ..
    } = condition
    else {
        panic!("expected postfix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_prefix_decrement_while_condition() {
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while_prefix_size".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "size".to_string(),
                ty: size_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "size".to_string(),
                        ty: size_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Dec,
                    prefix: true,
                    ty: size_ty.clone(),
                },
                body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                    value: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower prefix decrement condition");

    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", ir.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: true,
        ..
    } = condition
    else {
        panic!("expected prefix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

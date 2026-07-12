#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_bitand_array_index_expr() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
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
    let const_uint32_array_ty = ClangTypeSkeleton {
        spelled: "const uint32_t[256]".to_string(),
        canonical: "uint32_t[256]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(uint32_ty.clone()),
            len: Some(256),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_index".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "idx".to_string(),
                ty: uint32_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "table".to_string(),
                    ty: const_uint32_array_ty,
                }),
                index: Box::new(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::BitAnd,
                    lhs: Box::new(ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::BitXor,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "crc".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "idx".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        ty: uint32_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                        value: 255,
                        spelling: "255".to_string(),
                        ty: int_ty,
                    }),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower bitand array index");

    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return table index, got {:?}", ir.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        rhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 255, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_shift_right_expr() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
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
    let skeleton = ClangFunctionSkeleton {
        name: "crc_shift".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Shr,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 8,
                    spelling: "8".to_string(),
                    ty: int_ty,
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower shift right expression");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Shr,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected shift right return, got {:?}", ir.body);
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 8, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_simple_while_statement() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
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
                    ty: uint32_ty.clone(),
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower while statement");

    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", ir.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "crc"));
    let [IrStmt::Assign { target, value, .. }] = body.as_slice() else {
        panic!("expected one while-body assignment, got {body:?}");
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(value, IrExpr::Var { name, .. } if name == "crc"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_while_from_clang_lowered_ir() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                },
                body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::BitXor,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "crc".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::Unary {
                            op: ClangUnaryOperator::BitNot,
                            operand: Box::new(ClangExprSkeleton::IntegerLiteral {
                                value: 0,
                                spelling: "0U".to_string(),
                                ty: uint32_ty.clone(),
                            }),
                            ty: uint32_ty.clone(),
                        }),
                        ty: uint32_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower scalar while skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while from lowered IR");

    assert!(rust.contains("pub fn crc_while(mut crc: u32) -> u32"));
    assert!(rust.contains("while crc != 0u32 {"));
    assert!(rust.contains("crc = (crc ^ !0u32);"));
    assert!(rust.contains("return crc;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-scalar-while", &rust);
}

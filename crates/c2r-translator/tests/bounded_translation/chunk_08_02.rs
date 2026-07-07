#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_compound_assignment_integer_promotion() {
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
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
    let skeleton = ClangFunctionSkeleton {
        name: "inc8".to_string(),
        return_type: uint8_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: uint8_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::CompoundAssign {
                target: ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: uint8_ty.clone(),
                },
                op: ClangBinaryOperator::Add,
                value: ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: uint8_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: uint8_ty.clone(),
                }),
            },
        ],
    };

    let ir =
        lower_function_skeleton(&skeleton).expect("lower promoted compound assignment skeleton");

    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!(
            "expected promoted compound assignment followed by return, got {:?}",
            ir.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
    let IrExpr::Cast {
        target: cast_target,
        expr,
        implicit: true,
        ..
    } = value
    else {
        panic!("expected final truncation cast, got {value:?}");
    };
    assert!(matches!(
        &cast_target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
    let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr.as_ref()
    else {
        panic!("expected promoted binary, got {expr:?}");
    };
    assert_eq!(op, &IrBinOp::Add);
    assert!(matches!(
        &ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Cast {
            target,
            expr,
            implicit: true,
            ..
        } if matches!(&target.kind, IrTypeKind::Integer { signed: true, width: 32 })
            && matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "value")
    ));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 1, .. }));

    let rust =
        emit_rust_from_ir(&ir).expect("emit promoted compound assignment from lowered skeleton");
    assert!(rust.contains("pub fn inc8(mut value: u8) -> u8"));
    assert!(rust.contains(
        "value = ((value as i32).checked_add(1i32).expect(\"signed addition overflow\") as u8);"
    ));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-clang-compound-promotion", &rust);
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

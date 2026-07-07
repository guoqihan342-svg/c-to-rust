#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_left_shift_with_int_shift_count_from_clang_lowered_ir() {
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
        name: "shift_flags".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Shl,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: uint32_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 4,
                    spelling: "4".to_string(),
                    ty: int_ty,
                }),
                ty: uint32_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower shift with int count");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Shl,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected left-shift return, got {:?}", ir.body);
    };
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 4, spelling, ty, .. }
            if spelling == "4"
                && matches!(
                    ty.kind,
                    IrTypeKind::Integer {
                        signed: true,
                        width: 32
                    }
                )
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit left shift with int shift count");

    assert!(rust.contains("pub fn shift_flags(value: u32) -> u32"));
    assert!(rust.contains("return value.checked_shl(core::convert::TryFrom::try_from(4i32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\");"));
    assert_rust_snippet_compiles("typed-ir-clang-left-shift-int-count", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_signed_unary_minus_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "neg_value".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Unary {
                op: ClangUnaryOperator::Neg,
                operand: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower neg_value skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Unary {
                op: IrUnOp::Neg,
                operand,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-neg statement");
    };
    assert!(matches!(
        operand.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit neg_value from lowered typed IR");

    assert!(rust.contains("pub fn neg_value(value: i32) -> i32"));
    assert!(rust.contains("return (-value);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-signed-unary-minus", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_bitxor_bitnot_assignment() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_xor_not".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Assign {
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
                            spelling: "0".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        ty: uint32_ty.clone(),
                    }),
                    ty: uint32_ty.clone(),
                },
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower bitxor bitnot assignment");

    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!(
            "expected bitxor assignment followed by return, got {:?}",
            ir.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        lhs,
        rhs,
        ..
    } = value
    else {
        panic!("expected bitxor assignment value, got {value:?}");
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand,
        ..
    } = rhs.as_ref()
    else {
        panic!("expected bitnot rhs, got {rhs:?}");
    };
    assert!(
        matches!(operand.as_ref(), IrExpr::LitInt { value: 0, spelling, .. } if spelling == "0")
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_scalar_compound_assignment_family() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let cases = [
        (ClangBinaryOperator::Add, IrBinOp::Add, 1, "1"),
        (ClangBinaryOperator::Sub, IrBinOp::Sub, 2, "2"),
        (ClangBinaryOperator::Mul, IrBinOp::Mul, 3, "3"),
        (ClangBinaryOperator::Div, IrBinOp::Div, 4, "4"),
        (ClangBinaryOperator::Mod, IrBinOp::Mod, 5, "5"),
        (ClangBinaryOperator::BitAnd, IrBinOp::BitAnd, 7, "7"),
        (ClangBinaryOperator::BitOr, IrBinOp::BitOr, 8, "8"),
        (ClangBinaryOperator::BitXor, IrBinOp::BitXor, 9, "9"),
        (ClangBinaryOperator::Shl, IrBinOp::Shl, 1, "1"),
    ];
    let mut body = Vec::new();
    for (op, _, value, spelling) in &cases {
        body.push(ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::DeclRef {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
            op: op.clone(),
            value: ClangExprSkeleton::IntegerLiteral {
                value: *value,
                spelling: spelling.to_string(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        });
    }
    body.push(ClangStmtSkeleton::Return {
        value: Some(ClangExprSkeleton::DeclRef {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }),
    });
    let skeleton = ClangFunctionSkeleton {
        name: "compound_family".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body,
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower scalar compound assignment family");

    for (stmt, (_, expected_op, _, _)) in ir.body.iter().take(cases.len()).zip(cases.iter()) {
        let IrStmt::Assign { target, value, .. } = stmt else {
            panic!("expected desugared assignment, got {stmt:?}");
        };
        assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
        let IrExpr::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected compound assignment binary value, got {value:?}");
        };
        assert_eq!(op, expected_op);
        assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "value"));
        assert!(matches!(rhs.as_ref(), IrExpr::LitInt { .. }));
    }

    let rust = emit_rust_from_ir(&ir).expect("emit scalar compound assignment family");
    assert!(rust.contains("pub fn compound_family(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(
        rust.contains("value = value.checked_sub(2i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust
        .contains("value = value.checked_mul(3i32).expect(\"signed multiplication overflow\");"));
    assert!(rust.contains(
        "value = value.checked_div(4i32).expect(\"division by zero or signed overflow\");"
    ));
    assert!(rust.contains(
        "value = value.checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"
    ));
    assert!(rust.contains("value = (value & 7i32);"));
    assert!(rust.contains("value = (value | 8i32);"));
    assert!(rust.contains("value = (value ^ 9i32);"));
    assert!(rust.contains("value = value.checked_shl(core::convert::TryFrom::try_from(1i32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\");"));
    assert_rust_snippet_compiles("typed-ir-clang-compound-family", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_signed_right_shift_compound_assignment_without_contract() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "signed_shift_compound".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::CompoundAssign {
                target: ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                },
                op: ClangBinaryOperator::Shr,
                value: ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower signed right shift compound");

    let error = emit_rust_from_ir(&ir)
        .expect_err("signed right shift compound assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("signed right shift"));
    assert!(error.reason.contains("implementation-defined"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_record_field_compound_assignment() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let field_target = ClangExprSkeleton::Member {
        base: Box::new(ClangExprSkeleton::DeclRef {
            name: "p".to_string(),
            ty: point_ty.clone(),
        }),
        field: "x".to_string(),
        ty: int_ty.clone(),
        is_arrow: false,
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_point_x".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ty.clone(),
            },
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::CompoundAssign {
                target: field_target.clone(),
                op: ClangBinaryOperator::Add,
                value: ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::Return {
                value: Some(field_target.clone()),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton)
        .expect("lower by-value record field compound assignment");

    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!(
            "expected record field compound assignment followed by return, got {:?}",
            ir.body
        );
    };
    assert!(
        matches!(target, IrExpr::Member { field, is_arrow: false, .. } if field == "x"),
        "expected dot-field assignment target, got {target:?}"
    );
    let IrExpr::Binary { op, lhs, rhs, .. } = value else {
        panic!("expected compound assignment binary value, got {value:?}");
    };
    assert_eq!(op, &IrBinOp::Add);
    assert!(
        matches!(lhs.as_ref(), IrExpr::Member { field, is_arrow: false, .. } if field == "x"),
        "expected dot-field binary lhs, got {lhs:?}"
    );
    assert!(matches!(rhs.as_ref(), IrExpr::Var { name, .. } if name == "value"));

    let rust = emit_rust_from_ir(&ir).expect("emit record field compound assignment skeleton");
    assert!(rust.contains("pub fn add_point_x(mut p: Point, value: i32) -> i32"));
    assert!(rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-clang-record-field-compound", &rust);
}

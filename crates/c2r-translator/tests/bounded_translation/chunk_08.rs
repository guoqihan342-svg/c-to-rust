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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_record_field_compound_assignment_literal_and_cast_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
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
        name: "add_point_literals".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ty.clone(),
            },
            ClangParamSkeleton {
                name: "byte".to_string(),
                ty: uint8_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::CompoundAssign {
                target: field_target.clone(),
                op: ClangBinaryOperator::Add,
                value: ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::CompoundAssign {
                target: field_target.clone(),
                op: ClangBinaryOperator::Add,
                value: ClangExprSkeleton::Cast {
                    target: int_ty.clone(),
                    expr: Box::new(ClangExprSkeleton::DeclRef {
                        name: "byte".to_string(),
                        ty: uint8_ty,
                    }),
                    implicit: true,
                },
                result_ty: int_ty.clone(),
                compute_lhs_ty: int_ty.clone(),
                compute_result_ty: int_ty.clone(),
            },
            ClangStmtSkeleton::Return {
                value: Some(field_target),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton)
        .expect("lower by-value record field compound assignment literal/cast RHS");

    let rust = emit_rust_from_ir(&ir).expect("emit record field compound assignment literal/cast");
    assert!(rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(
        rust.contains("p.x = p.x.checked_add((byte as i32)).expect(\"signed addition overflow\");")
    );
    assert_rust_snippet_compiles("typed-ir-clang-record-field-compound-literal-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_complex_rhs() {
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
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_rhs".to_string(),
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
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
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
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject complex RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_call_rhs() {
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
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_call_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: point_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Call {
                callee: "helper".to_string(),
                args: Vec::new(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject call RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_member_rhs() {
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
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_member_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: point_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty.clone(),
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "y".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject member RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_index_rhs() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let int_array_ty = ClangTypeSkeleton {
        spelled: "int[4]".to_string(),
        canonical: "int[4]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(int_ty.clone()),
            len: Some(4),
        },
    };
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_index_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ty.clone(),
            },
            ClangParamSkeleton {
                name: "values".to_string(),
                ty: int_array_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "values".to_string(),
                    ty: int_array_ty,
                }),
                index: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject index RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_non_integer_rhs() {
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
    let point_ty = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_rhs_type".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ty.clone(),
            },
            ClangParamSkeleton {
                name: "ptr".to_string(),
                ty: int_ptr_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::DeclRef {
                name: "ptr".to_string(),
                ty: int_ptr_ty,
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let error = lower_function_skeleton(&skeleton)
        .expect_err("record field compound assignment must reject non-integer RHS");

    assert_eq!(error.kind, "unsupported_compound_assignment_value");
    assert!(error
        .message
        .contains("record field compound assignment RHS"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_deref_target() {
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
        name: "bad_record_field_compound_deref_target".to_string(),
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
        .expect_err("record field compound assignment must reject deref target");

    assert_eq!(error.kind, "unsupported_compound_assignment_target");
    assert!(error
        .message
        .contains("simple variable or by-value record field"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_index_target() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let int_array_ty = ClangTypeSkeleton {
        spelled: "int[4]".to_string(),
        canonical: "int[4]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(int_ty.clone()),
            len: Some(4),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_index_target".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "values".to_string(),
            ty: int_array_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "values".to_string(),
                    ty: int_array_ty,
                }),
                index: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: int_ty.clone(),
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
        .expect_err("record field compound assignment must reject index target");

    assert_eq!(error.kind, "unsupported_compound_assignment_target");
    assert!(error
        .message
        .contains("simple variable or by-value record field"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_mutable_record_pointer_field_compound_assignment() {
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
    let point_ptr_ty = ClangTypeSkeleton {
        spelled: "struct point *".to_string(),
        canonical: "struct point *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(point_ty.clone()),
            width: None,
        },
    };
    let void_ty = ClangTypeSkeleton {
        spelled: "void".to_string(),
        canonical: "void".to_string(),
        kind: ClangTypeKind::Void,
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_point_x".to_string(),
        return_type: void_ty,
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
            },
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: point_ptr_ty,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: true,
            },
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::DeclRef {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };

    let ir = lower_function_skeleton(&skeleton)
        .expect("lower mutable record pointer field compound assignment");

    let [IrStmt::Assign { target, value, .. }] = ir.body.as_slice() else {
        panic!(
            "expected mutable arrow field compound assignment, got {:?}",
            ir.body
        );
    };
    assert!(
        matches!(target, IrExpr::Member { field, is_arrow: true, .. } if field == "x"),
        "expected arrow member target, got {target:?}"
    );
    let IrExpr::Binary { op, lhs, rhs, .. } = value else {
        panic!("expected binary compound value, got {value:?}");
    };
    assert_eq!(op, &IrBinOp::Add);
    assert!(
        matches!(lhs.as_ref(), IrExpr::Member { field, is_arrow: true, .. } if field == "x"),
        "expected arrow member lhs, got {lhs:?}"
    );
    assert!(matches!(rhs.as_ref(), IrExpr::Var { name, .. } if name == "value"));

    let rust = emit_rust_from_ir(&ir)
        .expect("emit mutable record pointer field compound assignment skeleton");
    assert!(rust.contains("pub fn add_point_x(mut p: &mut Point, value: i32)"));
    assert!(rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles(
        "typed-ir-clang-mutable-record-pointer-field-compound",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_nested_base() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let outer_ty = ClangTypeSkeleton {
        spelled: "struct outer".to_string(),
        canonical: "struct outer".to_string(),
        kind: ClangTypeKind::Record {
            name: "outer".to_string(),
        },
    };
    let inner_ty = ClangTypeSkeleton {
        spelled: "struct inner".to_string(),
        canonical: "struct inner".to_string(),
        kind: ClangTypeKind::Record {
            name: "inner".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "bad_record_field_compound_nested_base".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: outer_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: ClangExprSkeleton::Member {
                base: Box::new(ClangExprSkeleton::Member {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "p".to_string(),
                        ty: outer_ty,
                    }),
                    field: "inner".to_string(),
                    ty: inner_ty,
                    is_arrow: false,
                }),
                field: "x".to_string(),
                ty: int_ty.clone(),
                is_arrow: false,
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
        .expect_err("record field compound assignment must reject nested base");

    assert_eq!(error.kind, "unsupported_compound_assignment_target");
    assert!(error.message.contains("direct record variable base"));
}

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

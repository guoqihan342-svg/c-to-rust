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

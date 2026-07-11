
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_rejects_record_field_compound_assignment_cast_and_compute_mismatch() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let uint_ty = ClangTypeSkeleton {
        spelled: "unsigned int".to_string(),
        canonical: "unsigned int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
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
    let bucket_ty = ClangTypeSkeleton {
        spelled: "struct renamed_bucket".to_string(),
        canonical: "struct renamed_bucket".to_string(),
        kind: ClangTypeKind::Record {
            name: "renamed_bucket".to_string(),
        },
    };
    let target = ClangExprSkeleton::Member {
        base: Box::new(ClangExprSkeleton::DeclRef {
            name: "bucket".to_string(),
            ty: bucket_ty.clone(),
        }),
        field: "count".to_string(),
        ty: int_ty.clone(),
        is_arrow: false,
    };
    let cast_mismatch = ClangFunctionSkeleton {
        name: "reject_pointer_cast_rhs".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "bucket".to_string(),
            ty: bucket_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target: target.clone(),
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::Cast {
                target: int_ptr_ty,
                expr: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                implicit: false,
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty.clone(),
            compute_result_ty: int_ty.clone(),
        }],
    };
    let cast_error = lower_function_skeleton(&cast_mismatch)
        .expect_err("record field compound assignment must reject non-integer cast target");
    assert_eq!(cast_error.kind, "unsupported_compound_assignment_value");
    assert!(cast_error
        .message
        .contains("RHS cast target must be an integer"));

    let compute_mismatch = ClangFunctionSkeleton {
        name: "reject_compute_type_mismatch".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "bucket".to_string(),
            ty: bucket_ty,
        }],
        body: vec![ClangStmtSkeleton::CompoundAssign {
            target,
            op: ClangBinaryOperator::Add,
            value: ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: int_ty.clone(),
            },
            result_ty: int_ty.clone(),
            compute_lhs_ty: int_ty,
            compute_result_ty: uint_ty,
        }],
    };
    let compute_error = lower_function_skeleton(&compute_mismatch)
        .expect_err("record field compound assignment must reject compute type mismatch");
    assert_eq!(compute_error.kind, "unsupported_compound_assignment_type");
    assert!(compute_error
        .message
        .contains("compute lhs/result types must match"));
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

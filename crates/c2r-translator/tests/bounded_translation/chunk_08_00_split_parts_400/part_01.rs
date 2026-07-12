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

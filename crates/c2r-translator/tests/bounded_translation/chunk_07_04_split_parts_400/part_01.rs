#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_builds_typed_ir_for_add_one_fixture() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
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
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    assert_eq!(ir.name, "add_one");
    assert!(matches!(
        ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Add,
                lhs,
                rhs,
                ty,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-add statement");
    };
    assert!(matches!(ty.kind, IrTypeKind::Integer { width: 32, .. }));
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_add_one_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
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
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit add_one from lowered typed IR");

    assert!(rust.contains("pub fn add_one(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-add-one", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_subtraction_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "sub_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Sub,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower sub_one skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Sub,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-sub statement");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit sub_one from lowered typed IR");

    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(
        rust.contains("return value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-sub-one", &rust);
}

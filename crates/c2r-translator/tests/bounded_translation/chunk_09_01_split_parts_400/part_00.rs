#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_pointer_cast_assignment() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_void_ty = ClangTypeSkeleton {
        spelled: "const void".to_string(),
        canonical: "void".to_string(),
        kind: ClangTypeKind::Void,
    };
    let const_void_ptr_ty = ClangTypeSkeleton {
        spelled: "const void *".to_string(),
        canonical: "void *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_void_ty),
            width: None,
        },
    };
    let const_uint8_ty = ClangTypeSkeleton {
        spelled: "const uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint8_t *".to_string(),
        canonical: "uint8_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint8_ty),
            width: None,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_assign_ptr".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "buf".to_string(),
                ty: const_void_ptr_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "p".to_string(),
                ty: const_uint8_ptr_ty.clone(),
                init: None,
            },
            ClangStmtSkeleton::Assign {
                target: ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: const_uint8_ptr_ty.clone(),
                },
                value: ClangExprSkeleton::Cast {
                    target: const_uint8_ptr_ty,
                    expr: Box::new(ClangExprSkeleton::DeclRef {
                        name: "buf".to_string(),
                        ty: const_void_ptr_ty,
                    }),
                    implicit: false,
                },
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower pointer cast assignment");

    let [IrStmt::Decl { .. }, IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] =
        ir.body.as_slice()
    else {
        panic!(
            "expected declaration, pointer cast assignment, return; got {:?}",
            ir.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "p"));
    match value {
        IrExpr::Cast {
            target,
            expr,
            implicit: false,
            ..
        } => {
            assert!(matches!(target.kind, IrTypeKind::Pointer { .. }));
            assert!(matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "buf"));
        }
        other => panic!("expected explicit cast value, got {other:?}"),
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_pointer_deref_expr() {
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ty = ClangTypeSkeleton {
        spelled: "const uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint8_t *".to_string(),
        canonical: "uint8_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint8_ty),
            width: None,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "read_byte".to_string(),
        return_type: uint8_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: const_uint8_ptr_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: const_uint8_ptr_ty,
                }),
                ty: uint8_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower pointer deref skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, ty, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return deref, got {:?}", ir.body);
    };
    assert!(matches!(ptr.as_ref(), IrExpr::Var { name, .. } if name == "p"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_pointer_add_deref_expr() {
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ty = ClangTypeSkeleton {
        spelled: "const uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint8_t *".to_string(),
        canonical: "uint8_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint8_ty),
            width: None,
        },
    };
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "read_byte_at".to_string(),
        return_type: uint8_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "p".to_string(),
                ty: const_uint8_ptr_ty.clone(),
            },
            ClangParamSkeleton {
                name: "i".to_string(),
                ty: size_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Add,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "p".to_string(),
                        ty: const_uint8_ptr_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "i".to_string(),
                        ty: size_ty,
                    }),
                    ty: const_uint8_ptr_ty,
                }),
                ty: uint8_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower pointer add deref skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, ty, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return pointer-add deref, got {:?}", ir.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ..
    } = ptr.as_ref()
    else {
        panic!("expected pointer-add deref ptr, got {ptr:?}");
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "p"));
    assert!(matches!(rhs.as_ref(), IrExpr::Var { name, .. } if name == "i"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
}

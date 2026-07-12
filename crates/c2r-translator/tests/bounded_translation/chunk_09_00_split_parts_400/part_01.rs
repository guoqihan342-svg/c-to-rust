#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_const_void_pointer_and_size_t_params() {
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
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_identity".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "buf".to_string(),
                ty: const_void_ptr_ty,
            },
            ClangParamSkeleton {
                name: "size".to_string(),
                ty: size_ty,
            },
        ],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::DeclRef {
                name: "crc".to_string(),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower crc_identity skeleton");

    assert_eq!(ir.params.len(), 3);
    match &ir.params[1].ty.kind {
        IrTypeKind::Pointer { pointee } => {
            assert!(!ir.params[1].ty.is_const);
            assert!(matches!(pointee.kind, IrTypeKind::Void));
            assert!(pointee.is_const);
        }
        other => panic!("expected pointer param, got {other:?}"),
    }
    assert!(matches!(
        ir.params[2].ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
    assert_eq!(ir.params[2].ty.canonical, "size_t");
    assert_eq!(ir.params[2].ty.width_bits, Some(64));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_const_uint8_pointer_decl() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
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
        name: "crc_decl".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "p".to_string(),
                ty: const_uint8_ptr_ty,
                init: None,
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower declaration skeleton");

    let [IrStmt::Decl { name, ty, init, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected declaration followed by return, got {:?}", ir.body);
    };
    assert_eq!(name, "p");
    assert!(init.is_none());
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => {
            assert!(!ty.is_const);
            assert!(matches!(
                pointee.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 8
                }
            ));
            assert!(pointee.is_const);
        }
        other => panic!("expected pointer declaration type, got {other:?}"),
    }
}

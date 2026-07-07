#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_logical_not_return_value() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "is_zero_value".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Unary {
                op: ClangUnaryOperator::Not,
                operand: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower logical not return value");

    let [IrStmt::Return {
        value: Some(IrExpr::Unary {
            op: IrUnOp::Not, ..
        }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected logical not return, got {:?}", ir.body);
    };

    let rust = emit_rust_from_ir(&ir).expect("emit logical not return from lowered IR");
    assert!(rust.contains("return (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-clang-return-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_emits_postfix_increment_value_decl_initializer() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "postfix_inc_value_decl".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "out".to_string(),
                ty: int_ty.clone(),
                init: Some(ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Inc,
                    prefix: false,
                    ty: int_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Add,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "out".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower postfix increment value decl");
    let rust = emit_rust_from_ir(&ir).expect("emit postfix increment value decl");

    assert!(rust.contains("pub fn postfix_inc_value_decl(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = post_inc_value;"));
    assert_rust_snippet_runs(
        "typed-ir-clang-postfix-inc-value-decl",
        &rust,
        "    assert_eq!(postfix_inc_value_decl(5), 11);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_if_from_clang_lowered_ir() {
    let skeleton = clang_scalar_if_skeleton();
    let ir = lower_function_skeleton(&skeleton).expect("lower scalar if skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if from lowered IR");

    assert!(rust.contains("pub fn adjust_if(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-scalar-if", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_postfix_decrement_condition() {
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while_size".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "size".to_string(),
                ty: size_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "size".to_string(),
                        ty: size_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Dec,
                    prefix: false,
                    ty: size_ty.clone(),
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
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower postfix decrement condition");

    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", ir.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ..
    } = condition
    else {
        panic!("expected postfix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_prefix_decrement_while_condition() {
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while_prefix_size".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "size".to_string(),
                ty: size_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "size".to_string(),
                        ty: size_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Dec,
                    prefix: true,
                    ty: size_ty.clone(),
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
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower prefix decrement condition");

    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", ir.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: true,
        ..
    } = condition
    else {
        panic!("expected prefix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_postfix_increment_in_deref_expr() {
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
        name: "read_byte_inc".to_string(),
        return_type: uint8_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: const_uint8_ptr_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "p".to_string(),
                        ty: const_uint8_ptr_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Inc,
                    prefix: false,
                    ty: const_uint8_ptr_ty,
                }),
                ty: uint8_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower postfix increment in deref skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, ty, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return deref, got {:?}", ir.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        panic!("expected postfix increment ptr, got {ptr:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "p"));
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
fn clang_lowering_skeleton_maps_array_subscript_expr() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_uint32_ty = ClangTypeSkeleton {
        spelled: "const uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_uint32_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint32_t *".to_string(),
        canonical: "uint32_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint32_ty),
            width: None,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "read_table".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "table".to_string(),
                ty: const_uint32_ptr_ty.clone(),
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
                    ty: const_uint32_ptr_ty,
                }),
                index: Box::new(ClangExprSkeleton::DeclRef {
                    name: "idx".to_string(),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower array subscript skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Index {
            base, index, ty, ..
        }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return table index, got {:?}", ir.body);
    };
    assert!(matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "table"));
    assert!(matches!(index.as_ref(), IrExpr::Var { name, .. } if name == "idx"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_const_array_type() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
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
        name: "read_table".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "idx".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "table".to_string(),
                    ty: const_uint32_array_ty,
                }),
                index: Box::new(ClangExprSkeleton::DeclRef {
                    name: "idx".to_string(),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower const array skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Index { base, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return table index, got {:?}", ir.body);
    };
    let IrExpr::Var { ty, .. } = base.as_ref() else {
        panic!("expected array base variable, got {base:?}");
    };
    assert!(ty.is_const);
    match &ty.kind {
        IrTypeKind::Array { element, len } => {
            assert_eq!(*len, Some(256));
            assert!(matches!(
                element.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ));
        }
        other => panic!("expected array base type, got {other:?}"),
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_report_records_unavailable_without_clang_path() {
    let environment = std::collections::BTreeMap::new();

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &PathBuf::from("add_one.c"),
        "add_one",
    );

    assert_eq!(report.status, "unavailable");
    assert_eq!(report.frontend, "clang");
    assert_eq!(report.function_name, "add_one");
    assert_eq!(report.source_file.as_deref(), Some("add_one.c"));
    assert_eq!(report.clang_path.as_deref(), None);
    assert!(report.function_ir.is_none());
    assert!(report
        .errors
        .iter()
        .any(|error| error.kind == "missing_clang_path"));
    assert!(report
        .diagnostics
        .iter()
        .any(|diagnostic| diagnostic.contains("CLANG_PATH is not set")));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_report_maps_unsupported_skeleton_without_ir() {
    let unsupported_type = ClangTypeSkeleton {
        spelled: "long double".to_string(),
        canonical: "long double".to_string(),
        kind: ClangTypeKind::Unsupported {
            reason: "long double is outside the current type skeleton".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "unsupported_value".to_string(),
        return_type: unsupported_type.clone(),
        params: vec![],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: unsupported_type,
            }),
        }],
    };
    let environment = std::collections::BTreeMap::new();

    let report = lower_function_skeleton_report(&skeleton, &environment);

    assert_eq!(report.status, "unsupported");
    assert_eq!(report.frontend, "clang");
    assert_eq!(report.function_name, "unsupported_value");
    assert!(report.function_ir.is_none());
    assert!(report
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_clang_type"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-add-one");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("add_one.c");
    fs::write(
        &source_file,
        "int add_one(int value) { return value + 1; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "add_one")
        .expect("lower real clang AST add_one");
    let environment = std::collections::BTreeMap::from([
        (
            "CLANG_PATH".to_string(),
            clang_path.to_string_lossy().into_owned(),
        ),
        (
            "LIBCLANG_PATH".to_string(),
            "tools/llvm/bin/libclang.so".to_string(),
        ),
    ]);
    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_one");

    assert_eq!(ir.name, "add_one");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Binary {
                op: IrBinOp::Add,
                ..
            }),
            ..
        }]
    ));
    assert_eq!(report.status, "lowered");
    assert_eq!(report.frontend, "clang");
    assert!(report.errors.is_empty(), "{:?}", report.errors);
    assert_eq!(
        report
            .function_ir
            .as_ref()
            .map(|function| function.name.as_str()),
        Some("add_one")
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_real_scalar_subtraction_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-sub-one");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sub_one.c");
    fs::write(
        &source_file,
        "int sub_one(int value) { return value - 1; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "sub_one")
        .expect("lower real clang AST sub_one");

    assert_eq!(ir.name, "sub_one");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Binary {
                op: IrBinOp::Sub,
                ..
            }),
            ..
        }]
    ));

    let emitted = emit_rust_from_ir(&ir).expect("emit real clang sub_one from typed IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(
        rust.contains("return value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-scalar-subtraction", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_real_scalar_mul_div_mod_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mul-div-mod");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mul_div_mod.c");
    fs::write(
        &source_file,
        "int mul_div_mod(int value) { return ((value * 3) / 2) % 5; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "mul_div_mod")
        .expect("lower real clang AST mul_div_mod");

    assert_eq!(ir.name, "mul_div_mod");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Binary {
                op: IrBinOp::Mod,
                ..
            }),
            ..
        }]
    ));

    let emitted = emit_rust_from_ir(&ir).expect("emit real clang mul_div_mod from typed IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn mul_div_mod(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_mul(3i32).expect(\"signed multiplication overflow\").checked_div(2i32).expect(\"division by zero or signed overflow\").checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-scalar-mul-div-mod", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_real_signed_unary_minus_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-neg-value");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("neg_value.c");
    fs::write(
        &source_file,
        "int neg_value(int value) { return -value; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "neg_value")
        .expect("lower real clang AST neg_value");

    assert_eq!(ir.name, "neg_value");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Unary {
                op: IrUnOp::Neg,
                ..
            }),
            ..
        }]
    ));

    let emitted = emit_rust_from_ir(&ir).expect("emit real clang neg_value from typed IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn neg_value(value: i32) -> i32"));
    assert!(rust.contains("return (-value);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-signed-unary-minus", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_parse_spec_report_uses_include_paths_for_real_ast_dump_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let source_root = unique_out_dir("clang-parse-spec-include-path");
    let include_dir = source_root.join("inc");
    let source_dir = source_root.join("src");
    fs::create_dir_all(&include_dir).unwrap();
    fs::create_dir_all(&source_dir).unwrap();
    fs::write(
        include_dir.join("fixture_config.h"),
        "int add_one(int value);\n#define ADD_ONE_OFFSET 1\n",
    )
    .unwrap();
    fs::write(
        source_dir.join("add_one.c"),
        "#include <fixture_config.h>\nint add_one(int value) { return value + ADD_ONE_OFFSET; }\n",
    )
    .unwrap();
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "source-sha",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + ADD_ONE_OFFSET; }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root.to_string_lossy().replace('\\', "/"),
        "source_file": "src/add_one.c",
        "source_file_hashes": {
            "src/add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/add_one.c",
            "line_start": 2,
            "line_end": 2,
            "byte_start": 28,
            "byte_end": 83,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "compiler_command_source": "unit-test",
            "clang_available": true
        }
    }))
    .unwrap();
    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_parse_spec_report(&environment, &parse_spec);

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.errors.is_empty(), "{:?}", report.errors);
    assert!(report.arguments.iter().any(|argument| {
        argument
            == &format!(
                "-I{}",
                source_root.join("inc").to_string_lossy().replace('\\', "/")
            )
    }));
    assert_eq!(
        report
            .function_ir
            .as_ref()
            .map(|function| function.name.as_str()),
        Some("add_one")
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_uint32_integer_type_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-uint32-add-one");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("add_one.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t add_one(uint32_t value) { return value + 1; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_one");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert!(matches!(
        function.return_type.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    assert!(matches!(
        function.params[0].ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_const_void_pointer_and_size_t_params_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-void-size");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_identity.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\n#include <stdint.h>\nuint32_t crc_identity(uint32_t crc, const void *buf, size_t size) { return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_identity");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert_eq!(function.params.len(), 3);
    match &function.params[1].ty.kind {
        IrTypeKind::Pointer { pointee } => {
            assert!(!function.params[1].ty.is_const);
            assert!(matches!(pointee.kind, IrTypeKind::Void));
            assert!(pointee.is_const);
        }
        other => panic!("expected pointer param, got {other:?}"),
    }
    assert!(matches!(
        function.params[2].ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_const_uint8_pointer_decl_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-u8-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_decl.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_decl(uint32_t crc, const void *buf) { const uint8_t *p; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, ty, init, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected declaration followed by return, got {:?}",
            function.body
        );
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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_assignment_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-assignment-stmt");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_assign.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_assign(uint32_t crc) { crc = crc; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_assign");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(value, IrExpr::Var { name, .. } if name == "crc"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_pointer_cast_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-cast-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_assign_ptr.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_assign_ptr(uint32_t crc, const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_assign_ptr");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, init, .. }, IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected declaration, pointer cast assignment, return; got {:?}",
            function.body
        );
    };
    assert_eq!(name, "p");
    assert!(init.is_none());
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
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_pointer_deref_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-deref");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte(const uint8_t *p) { return *p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_byte");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, ty, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected deref return, got {:?}", function.body);
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
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_pointer_deref_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-deref-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte(const uint8_t *p) { return *p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_byte");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit pointer deref return from real clang AST");
    let rust = &emitted.rust;
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_byte(p: &[u8]) -> u8"));
    assert!(rust.contains("return p[0usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-pointer-deref-emit", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_pointer_add_deref_return_values_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-add-deref-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_offset.c");
    fs::write(
        &source_file,
        concat!(
            "#include <stdint.h>\n",
            "#include <stddef.h>\n",
            "uint8_t read_pi(const uint8_t *p, size_t i) { return *(p + i); }\n",
            "uint8_t read_ip(const uint8_t *p, size_t i) { return *(i + p); }\n",
            "uint8_t read_p1(const uint8_t *p) { return *(p + 1); }\n",
        ),
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    for (function_name, signature, return_expr) in [
        (
            "read_pi",
            "pub fn read_pi(p: &[u8], i: usize) -> u8",
            "return p[i as usize];",
        ),
        (
            "read_ip",
            "pub fn read_ip(p: &[u8], i: usize) -> u8",
            "return p[i as usize];",
        ),
        (
            "read_p1",
            "pub fn read_p1(p: &[u8]) -> u8",
            "return p[1i32 as usize];",
        ),
    ] {
        let report =
            lower_function_from_clang_ast_dump_report(&environment, &source_file, function_name);

        assert_eq!(
            report.status, "lowered",
            "{function_name}: {:?}",
            report.errors
        );
        let function = report.function_ir.as_ref().expect("function ir");
        let emitted = emit_rust_from_ir(function)
            .unwrap_or_else(|error| panic!("{function_name}: {}", error.reason));
        let rust = &emitted.rust;
        assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
        assert!(rust.contains(signature), "{function_name}: {rust}");
        assert!(rust.contains(return_expr), "{function_name}: {rust}");
        assert_rust_snippet_compiles(
            &format!("typed-ir-real-clang-pointer-add-deref-emit-{function_name}"),
            rust,
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_pointer_add_deref_logical_not_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-add-deref-logical-not-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("offset_is_zero_not.c");
    fs::write(
        &source_file,
        concat!(
            "#include <stdint.h>\n",
            "#include <stddef.h>\n",
            "int offset_is_zero_not(const uint8_t *p, size_t i) {\n",
            "    if (!*(p + i)) { return 1; }\n",
            "    return 0;\n",
            "}\n",
        ),
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "offset_is_zero_not");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit pointer add deref logical-not if from clang AST");
    let rust = &emitted.rust;
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn offset_is_zero_not(p: &[u8], i: usize) -> i32"));
    assert!(rust.contains("if p[i as usize] == 0u8 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-pointer-add-deref-logical-not-if", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_postfix_increment_deref_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-deref");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_inc.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_inc(const uint8_t *p) { return *p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_byte_inc");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected deref return, got {:?}", function.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        panic!("expected postfix increment ptr, got {ptr:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "p"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_deref_in_bitand_array_index_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-deref-bitand-array-index");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_index_deref.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_index_deref(uint32_t crc, const uint8_t *p) { return table[(crc ^ *p) & 0xff]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_index_deref");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        rhs,
        ..
    } = lhs.as_ref()
    else {
        panic!("expected bitxor lhs, got {lhs:?}");
    };
    assert!(matches!(
        without_implicit_cast(rhs.as_ref()),
        IrExpr::Deref { .. }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_postfix_increment_deref_in_bitand_array_index_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-deref-bitand-array-index");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_index_postinc.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_index_postinc(uint32_t crc, const uint8_t *p) { return table[(crc ^ *p++) & 0xff]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_index_postinc");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        rhs,
        ..
    } = lhs.as_ref()
    else {
        panic!("expected bitxor lhs, got {lhs:?}");
    };
    let IrExpr::Deref { ptr, .. } = without_implicit_cast(rhs.as_ref()) else {
        panic!("expected deref rhs, got {rhs:?}");
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        panic!("expected postfix increment ptr, got {ptr:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "p"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_shift_right_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-shift-right");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_shift.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_shift(uint32_t crc) { return crc >> 8; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_shift");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Shr,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected shift right return, got {:?}", function.body);
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 8, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_bit_or_and_left_shift_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-bit-or-left-shift");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pack_flags.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t pack_flags(uint32_t value) { return (value << 4) | 3U; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "pack_flags");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::BitOr,
                lhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected bit-or return, got {:?}", function.body);
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Shl,
            ..
        }
    ));

    let rust = emit_rust_from_ir(function).expect("emit bit-or left-shift from real clang AST");
    assert!(rust.contains("pub fn pack_flags(value: u32) -> u32"));
    assert!(rust.contains("checked_shl"));
    assert!(rust.contains("|"));
    assert_rust_snippet_compiles("typed-ir-real-clang-bit-or-left-shift", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_crc_update_expr_with_postinc_and_shift_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-crc-update-postinc-shift");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_update_expr.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_update_expr(uint32_t crc, const uint8_t *p) { return table[(crc ^ *p++) & 0xff] ^ (crc >> 8); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_update_expr");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::BitXor,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected crc update return, got {:?}", function.body);
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Index { .. }));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Shr,
            ..
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_const_pointer_table_index_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-pointer-table-index-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t read_table(const uint32_t *table, uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit const pointer table index");
    assert!(rust.contains("pub fn read_table(table: &[u32], idx: u32) -> u32"));
    assert!(rust.contains("return table[idx as usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-const-pointer-table-index", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_const_void_byte_cursor_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-void-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_from_void.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_from_void(const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return *p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "read_byte_from_void",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit const void byte cursor read");
    assert!(rust.contains("pub fn read_byte_from_void(buf: &[u8]) -> u8"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return byte0;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-const-void-byte-cursor-read", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_nested_const_void_byte_cursor_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-const-void-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_byte.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_byte(uint32_t crc, const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return crc ^ (uint32_t)*p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_byte");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit nested const void byte cursor read");
    assert!(rust.contains("pub fn crc_xor_byte(crc: u32, buf: &[u8]) -> u32"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-const-void-byte-cursor-read",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_nested_const_u8_byte_cursor_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-const-u8-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_byte_from_u8.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_byte_from_u8(uint32_t crc, const uint8_t *p) { return crc ^ (uint32_t)*p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "crc_xor_byte_from_u8",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit nested const u8 byte cursor read");
    assert!(rust.contains("pub fn crc_xor_byte_from_u8(crc: u32, p: &[u8]) -> u32"));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-const-u8-byte-cursor-read",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_crc_update_assignment_with_pointer_table_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-crc-update-assignment-pointer-table-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("update_crc_step_from_clang.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t update_crc_step_from_clang(uint32_t crc, const uint8_t *p, const uint32_t *table) { crc = table[(crc ^ (uint32_t)*p++) & 0xffU] ^ (crc >> 8U); return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "update_crc_step_from_clang",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit clang crc update assignment with pointer table");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains(
        "pub fn update_crc_step_from_clang(mut crc: u32, p: &[u8], table: &[u32]) -> u32"
    ));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(rust.contains("crc = (table[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ crc.checked_shr(core::convert::TryFrom::try_from(8u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\"));"));
    assert!(rust.contains("return crc;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-crc-update-assignment-pointer-table",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_flashdb_crc32_from_lowered_ir_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-flashdb-crc32-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("fdb_utils.c");
    let table_values = repeated_c_u32_initializer(256, "0U");
    fs::write(
        &source_file,
        format!(
            "#include <stdint.h>\n#include <stddef.h>\nstatic const uint32_t crc32_table[256] = {{ {table_values} }};\nuint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) {{\n    const uint8_t *p;\n    p = (const uint8_t *)buf;\n    crc = crc ^ ~0U;\n    while (size--) {{\n        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);\n    }}\n    return crc ^ ~0U;\n}}\n"
        ),
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "fdb_calc_crc32");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert_eq!(report.globals.len(), 1);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit rust from real clang-lowered crc32 ir");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 0u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ crc.checked_shr("));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-flashdb-crc32-generic", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_parse_spec_emits_real_flashdb_crc32_from_lowered_ir_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let real_spec_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../validation/slice-specs/flashdb-real-fdb-calc-crc32.json");
    let real_spec: Value = serde_json::from_str(
        &fs::read_to_string(&real_spec_path).expect("read real fdb slice spec"),
    )
    .expect("parse real fdb slice spec");
    let source_file = "src/fdb_utils.c";
    let function_source_span = serde_json::from_value(
        real_spec
            .pointer("/c_boundary/signatures/0/source_span")
            .expect("function source span")
            .clone(),
    )
    .expect("parse function source span");
    let spec = SliceSpec {
        target_id: real_spec["target_id"].as_str().unwrap().to_string(),
        slice_id: real_spec["slice_id"].as_str().unwrap().to_string(),
        source_commit: real_spec["source_commit"].as_str().unwrap().to_string(),
        function_name: real_spec["function_name"].as_str().unwrap().to_string(),
        c_source: real_spec["c_source"].as_str().unwrap().to_string(),
        fixture_hash: real_spec["fixture_hash"].as_str().unwrap().to_string(),
        source_root: Some(
            real_spec["source"]["source_root"]
                .as_str()
                .unwrap()
                .to_string(),
        ),
        source_file: Some(source_file.to_string()),
        source_file_hashes: std::collections::BTreeMap::from([(
            source_file.to_string(),
            real_spec["source"]["source_file_hashes"][source_file]
                .as_str()
                .unwrap()
                .to_string(),
        )]),
        function_source_span: Some(function_source_span),
        build_profile: BuildProfile {
            include_paths: vec!["inc".to_string(), "tests".to_string()],
            defines: Vec::new(),
            target: None,
            clang_ast_fixture: None,
            target_triple: None,
            abi: None,
            compiler_command_source: "real-flashdb-slice-spec-test".to_string(),
            clang_available: true,
        },
        ..SliceSpec::default()
    };
    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_parse_spec_report(&environment, &parse_spec);

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.errors.is_empty(), "{:?}", report.errors);
    assert!(report.globals.iter().any(|global| {
        global.name == "crc32_table"
            && matches!(global.ty.kind, IrTypeKind::Array { len: Some(256), .. })
    }));
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit rust from real fdb clang-lowered ir");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 1996959894u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ crc.checked_shr("));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-flashdb-crc32-generic", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_array_subscript_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-array-subscript");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t read_table(const uint32_t *table, uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index {
            base, index, ty, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    assert!(matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "table"));
    assert!(matches!(index.as_ref(), IrExpr::Var { name, .. } if name == "idx"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_global_const_array_subscript_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-global-array-subscript");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { base, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected global array subscript return, got {:?}",
            function.body
        );
    };
    let IrExpr::Var { name, ty, .. } = base.as_ref() else {
        panic!("expected table variable, got {base:?}");
    };
    assert_eq!(name, "table");
    assert!(ty.is_const);
    assert!(matches!(ty.kind, IrTypeKind::Array { len: Some(256), .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_records_static_const_integer_array_global_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-global-array-initializer");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table_init.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[4] = { 1U, 2U, 0xEDB88320U, 4U };\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert_eq!(report.globals.len(), 1);
    let global = &report.globals[0];
    assert_eq!(global.name, "table");
    assert!(global.ty.is_const);
    assert!(matches!(
        global.ty.kind,
        IrTypeKind::Array { len: Some(4), .. }
    ));
    assert_eq!(
        global.init,
        IrGlobalInit::IntegerArray(vec![1, 2, 0xEDB8_8320, 4])
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_loop_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-loop");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sum_to_limit.c");
    fs::write(
        &source_file,
        "int sum_to_limit(int limit) { int total = 0; for (int i = 0; i < limit; i++) { total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "sum_to_limit");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, .. }, IrStmt::For {
        init, step, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert_eq!(name, "total");
    assert!(matches!(init.as_slice(), [IrStmt::Decl { name, .. }] if name == "i"));
    assert!(matches!(step.as_deref(), Some(IrStmt::Assign { .. })));
    assert!(matches!(body.as_slice(), [IrStmt::Assign { .. }]));

    let rust = emit_rust_from_ir(function).expect("emit typed IR for loop from real clang AST");
    assert!(rust.contains("pub fn sum_to_limit(limit: i32) -> i32"));
    assert!(rust.contains("{\n        let mut i: i32 = 0i32;\n        while (i < limit) {"));
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\");"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-for-loop", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_continue_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-continue");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_for_continue.c");
    fs::write(
        &source_file,
        "int bad_for_continue(int limit) { int total = 0; for (int i = 0; i < limit; i++) { if (i) { continue; } total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_for_continue");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { .. }, IrStmt::For { body, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Continue { .. }])
    ));

    let rust = emit_rust_from_ir(function).expect("emit typed IR for continue from real clang AST");
    assert!(rust.contains("pub fn bad_for_continue(limit: i32) -> i32"));
    assert!(rust.contains("if i != 0i32 {"));
    assert!(
        rust.contains("                i = i.checked_add(1i32).expect(\"signed addition overflow\");\n                continue;"),
        "{rust:?}"
    );
    assert_eq!(
        rust.matches("i = i.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust:?}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-for-continue", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_while_break_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-while-break");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("stop_at_limit.c");
    fs::write(
        &source_file,
        "int stop_at_limit(int value) { while (value) { if (value > 3) { break; } value = value - 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "stop_at_limit");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { body, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Break { .. }])
    ));

    let rust = emit_rust_from_ir(function).expect("emit typed IR while break from real clang AST");
    assert!(rust.contains("pub fn stop_at_limit(mut value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("if (value > 3i32) {"));
    assert!(rust.contains("break;"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-break", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_while_continue_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-while-continue");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("skip_once.c");
    fs::write(
        &source_file,
        "int skip_once(int value) { while (value) { value = value - 1; if (value > 3) { continue; } value = value - 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "skip_once");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { body, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { .. }, IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Continue { .. }])
    ));

    let rust =
        emit_rust_from_ir(function).expect("emit typed IR while continue from real clang AST");
    assert!(rust.contains("pub fn skip_once(mut value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("continue;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-continue", &rust);
}

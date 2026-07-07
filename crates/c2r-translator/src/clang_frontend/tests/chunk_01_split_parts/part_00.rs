    #[test]
    fn expr_skeleton_from_ast_allows_const_void_bitcast_direct_call_arg() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "struct fdb_blob *" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "struct fdb_blob *(*)(struct fdb_blob *, const void *, size_t)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct fdb_blob *(struct fdb_blob *, const void *, size_t)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "fdb_blob_make"
                            }
                        }
                    ]
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "&",
                    "type": { "qualType": "struct fdb_blob *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct fdb_blob" },
                            "referencedDecl": { "name": "blob" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "BitCast",
                    "type": { "qualType": "const void *" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "const char *" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "const char *" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "CallExpr",
                    "type": { "qualType": "__size_t" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "FunctionToPointerDecay",
                            "type": { "qualType": "__size_t (*)(const char *)" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "__size_t (const char *)" },
                                    "referencedDecl": {
                                        "kind": "FunctionDecl",
                                        "name": "strlen"
                                    }
                                }
                            ]
                        },
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "const char *" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "const char *" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton =
            expr_skeleton_from_ast(&expr).expect("record pointer constructor bitcast skeleton");
        let ClangExprSkeleton::Call { callee, args, .. } = &skeleton else {
            panic!("expected fdb_blob_make call skeleton, got {skeleton:?}");
        };
        assert_eq!(callee, "fdb_blob_make");
        let [ClangExprSkeleton::AddrOf { .. }, ClangExprSkeleton::DeclRef { name, .. }, ClangExprSkeleton::Call {
            callee: strlen,
            args: strlen_args,
            ..
        }] = args.as_slice()
        else {
            panic!("expected address, bitcast-stripped value, and strlen args, got {args:?}");
        };
        assert_eq!(name, "value");
        assert_eq!(strlen, "strlen");
        assert!(matches!(
            strlen_args.as_slice(),
            [ClangExprSkeleton::DeclRef { name, .. }] if name == "value"
        ));
        assert_eq!(bounded_call_args_rejection_reason(&[skeleton]), None);
    }

    #[test]
    fn bounded_call_args_allow_record_pointer_constructor_with_strlen_leaf() {
        let i32_ty = ClangTypeSkeleton {
            spelled: "int".to_string(),
            canonical: "int".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 32,
            },
        };
        let usize_ty = ClangTypeSkeleton {
            spelled: "size_t".to_string(),
            canonical: "size_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 64,
            },
        };
        let u8_ty = ClangTypeSkeleton {
            spelled: "const uint8_t".to_string(),
            canonical: "const unsigned char".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 8,
            },
        };
        let const_u8_ptr_ty = ClangTypeSkeleton {
            spelled: "const uint8_t *".to_string(),
            canonical: "const unsigned char *".to_string(),
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(u8_ty),
                width: Some(64),
            },
        };
        let blob_ty = ClangTypeSkeleton {
            spelled: "struct fdb_blob".to_string(),
            canonical: "struct fdb_blob".to_string(),
            kind: ClangTypeKind::Record {
                name: "fdb_blob".to_string(),
            },
        };
        let blob_ptr_ty = ClangTypeSkeleton {
            spelled: "struct fdb_blob *".to_string(),
            canonical: "struct fdb_blob *".to_string(),
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(blob_ty.clone()),
                width: Some(64),
            },
        };
        let nested = ClangExprSkeleton::Call {
            callee: "fdb_blob_make".to_string(),
            args: vec![
                ClangExprSkeleton::AddrOf {
                    operand: Box::new(ClangExprSkeleton::DeclRef {
                        name: "blob".to_string(),
                        ty: blob_ty,
                    }),
                    ty: blob_ptr_ty.clone(),
                },
                ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: const_u8_ptr_ty.clone(),
                },
                ClangExprSkeleton::Call {
                    callee: "strlen".to_string(),
                    args: vec![ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: const_u8_ptr_ty,
                    }],
                    ty: usize_ty,
                },
            ],
            ty: blob_ptr_ty,
        };

        assert_eq!(bounded_call_args_rejection_reason(&[nested]), None);

        let bad_nested = ClangExprSkeleton::Call {
            callee: "fdb_blob_make".to_string(),
            args: vec![
                ClangExprSkeleton::AddrOf {
                    operand: Box::new(ClangExprSkeleton::DeclRef {
                        name: "blob".to_string(),
                        ty: ClangTypeSkeleton {
                            spelled: "struct fdb_blob".to_string(),
                            canonical: "struct fdb_blob".to_string(),
                            kind: ClangTypeKind::Record {
                                name: "fdb_blob".to_string(),
                            },
                        },
                    }),
                    ty: ClangTypeSkeleton {
                        spelled: "struct fdb_blob *".to_string(),
                        canonical: "struct fdb_blob *".to_string(),
                        kind: ClangTypeKind::Pointer {
                            pointee: Box::new(ClangTypeSkeleton {
                                spelled: "struct fdb_blob".to_string(),
                                canonical: "struct fdb_blob".to_string(),
                                kind: ClangTypeKind::Record {
                                    name: "fdb_blob".to_string(),
                                },
                            }),
                            width: Some(64),
                        },
                    },
                },
                ClangExprSkeleton::Call {
                    callee: "helper_len".to_string(),
                    args: vec![],
                    ty: ClangTypeSkeleton {
                        spelled: "size_t".to_string(),
                        canonical: "size_t".to_string(),
                        kind: ClangTypeKind::Integer {
                            signed: false,
                            width: 64,
                        },
                    },
                },
            ],
            ty: ClangTypeSkeleton {
                spelled: "struct fdb_blob *".to_string(),
                canonical: "struct fdb_blob *".to_string(),
                kind: ClangTypeKind::Pointer {
                    pointee: Box::new(ClangTypeSkeleton {
                        spelled: "struct fdb_blob".to_string(),
                        canonical: "struct fdb_blob".to_string(),
                        kind: ClangTypeKind::Record {
                            name: "fdb_blob".to_string(),
                        },
                    }),
                    width: Some(64),
                },
            },
        };
        let reason = bounded_call_args_rejection_reason(&[bad_nested])
            .expect("unmodeled nested constructor call arg must fail closed");
        assert!(
            reason.contains("nested call expressions are outside the bounded call subset"),
            "{reason}"
        );

        let non_nested = ClangExprSkeleton::DeclRef {
            name: "status".to_string(),
            ty: i32_ty,
        };
        assert_eq!(bounded_call_args_rejection_reason(&[non_nested]), None);
    }

    #[test]
    fn stmt_skeleton_from_ast_lowers_direct_call_expr_statement() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (int)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "observe"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("direct call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower direct call statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected IR expr call statement, got {ir:?}");
        };
        assert_eq!(callee, "observe");
        let [arg] = args.as_slice() else {
            panic!("expected one direct call statement argument, got {args:?}");
        };
        assert_ir_lvalue_to_rvalue_var(arg, "value", true, 32);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_direct_call_arg_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void (*)(uint32_t)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (uint32_t)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "observe"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "uint8_t" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "uint8_t" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("direct call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower direct call statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected IR expr call statement, got {ir:?}");
        };
        assert_eq!(callee, "observe");
        let [IrExpr::Cast {
            target,
            expr,
            implicit,
            ..
        }] = args.as_slice()
        else {
            panic!("expected direct call argument cast, got {args:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(expr.as_ref(), "value", false, 8);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_direct_call_arg_integral_promotion() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (int)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "observe"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralPromotion",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "uint8_t" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "uint8_t" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("direct call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower direct call statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected IR expr call statement, got {ir:?}");
        };
        assert_eq!(callee, "observe");
        let [IrExpr::Cast {
            target,
            expr,
            implicit,
            ..
        }] = args.as_slice()
        else {
            panic!("expected direct call argument promotion, got {args:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(expr.as_ref(), "value", false, 8);
    }

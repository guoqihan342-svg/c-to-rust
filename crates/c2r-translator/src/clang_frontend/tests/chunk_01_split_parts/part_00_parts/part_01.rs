
    #[test]
    fn bounded_call_args_allow_direct_null_pointer_arg() {
        let void_ty = ClangTypeSkeleton {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        };
        let void_ptr_ty = ClangTypeSkeleton {
            spelled: "void *".to_string(),
            canonical: "void *".to_string(),
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(void_ty),
                width: Some(64),
            },
        };
        let null_arg = ClangExprSkeleton::NullPtr { ty: void_ptr_ty };

        assert_eq!(bounded_call_args_rejection_reason(&[null_arg]), None);
    }

    #[test]
    fn integral_to_boolean_literal_cast_becomes_bool_integer_literal() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "IntegralToBoolean",
            "type": { "qualType": "bool" },
            "inner": [
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "42"
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("integral-to-bool literal skeleton");
        let ClangExprSkeleton::IntegerLiteral { value, spelling, ty } = skeleton else {
            panic!("expected bool integer literal, got {skeleton:?}");
        };
        assert_eq!(value, 1);
        assert_eq!(spelling, "1");
        assert_eq!(ty.canonical, "_Bool");
        assert_eq!(bounded_call_args_rejection_reason(&[
            ClangExprSkeleton::IntegerLiteral { value, spelling, ty }
        ]), None);
    }

    #[test]
    fn bounded_call_args_allow_record_pointer_constructor_with_unbound_unsigned_long_strlen_leaf() {
        let const_char_ty = ClangTypeSkeleton {
            spelled: "const char".to_string(),
            canonical: "char".to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: "char requires target ABI width provenance before typed IR lowering"
                    .to_string(),
            },
        };
        let const_char_ptr_ty = ClangTypeSkeleton {
            spelled: "const char *".to_string(),
            canonical: "char *".to_string(),
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(const_char_ty),
                width: None,
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
                width: None,
            },
        };
        let strlen_unbound_size_t_ty = ClangTypeSkeleton {
            spelled: "unsigned long".to_string(),
            canonical: "unsigned long".to_string(),
            kind: ClangTypeKind::Unsupported {
                reason:
                    "unsigned long requires target ABI width provenance before typed IR lowering"
                        .to_string(),
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
                    ty: const_char_ptr_ty.clone(),
                },
                ClangExprSkeleton::Call {
                    callee: "strlen".to_string(),
                    args: vec![ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: const_char_ptr_ty,
                    }],
                    ty: strlen_unbound_size_t_ty,
                },
            ],
            ty: blob_ptr_ty,
        };

        assert_eq!(bounded_call_args_rejection_reason(&[nested]), None);
    }

    #[test]
    fn bounded_call_args_allow_immediate_nested_pointer_return_call() {
        let void_ty = ClangTypeSkeleton {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        };
        let db_ty = ClangTypeSkeleton {
            spelled: "fdb_kvdb_t".to_string(),
            canonical: "void *".to_string(),
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(void_ty),
                width: None,
            },
        };
        let const_char_ty = ClangTypeSkeleton {
            spelled: "const char".to_string(),
            canonical: "char".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 8,
            },
        };
        let const_char_ptr_ty = ClangTypeSkeleton {
            spelled: "const char *".to_string(),
            canonical: "char *".to_string(),
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(const_char_ty),
                width: None,
            },
        };
        let nested = ClangExprSkeleton::Call {
            callee: "db_name".to_string(),
            args: vec![ClangExprSkeleton::DeclRef {
                name: "db".to_string(),
                ty: db_ty,
            }],
            ty: const_char_ptr_ty,
        };

        assert_eq!(bounded_call_args_rejection_reason(&[nested]), None);
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

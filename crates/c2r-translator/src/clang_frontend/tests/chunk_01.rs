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

    #[test]
    fn stmt_skeleton_from_ast_accepts_compound_assignment_integer_promotion() {
        let stmt = serde_json::json!({
            "kind": "CompoundAssignOperator",
            "opcode": "+=",
            "type": { "qualType": "unsigned char" },
            "computeLHSType": { "qualType": "int" },
            "computeResultType": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned char" },
                    "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "x"
                    }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": {
                                "kind": "ParmVarDecl",
                                "name": "y"
                            }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("compound assignment skeleton");

        let ClangStmtSkeleton::CompoundAssign {
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            value,
            ..
        } = skeleton
        else {
            panic!("expected promoted compound assignment skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            result_ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 8
            }
        ));
        assert!(matches!(
            compute_lhs_ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert_eq!(compute_lhs_ty, compute_result_ty);
        assert_lvalue_to_rvalue_decl_ref(&value, "y", true, 32);
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_inc_dec_statement_as_assignment() {
        for (case_name, opcode, is_postfix, expected_op) in [
            ("postfix increment", "++", true, ClangBinaryOperator::Add),
            ("prefix increment", "++", false, ClangBinaryOperator::Add),
            ("postfix decrement", "--", true, ClangBinaryOperator::Sub),
            ("prefix decrement", "--", false, ClangBinaryOperator::Sub),
        ] {
            let stmt = serde_json::json!({
                "kind": "UnaryOperator",
                "opcode": opcode,
                "isPostfix": is_postfix,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "int" },
                        "referencedDecl": { "name": "value" }
                    }
                ]
            });

            let skeleton = stmt_skeleton_from_ast(&stmt).expect(case_name);
            let ClangStmtSkeleton::Assign { target, value } = skeleton else {
                panic!("{case_name}: expected assignment statement, got {skeleton:?}");
            };
            assert!(matches!(target, ClangExprSkeleton::DeclRef { name, .. } if name == "value"));
            let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
                panic!("{case_name}: expected binary assignment value, got {value:?}");
            };
            assert_eq!(op, expected_op);
            assert!(
                matches!(lhs.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "value")
            );
            assert!(matches!(
                rhs.as_ref(),
                ClangExprSkeleton::IntegerLiteral { value: 1, .. }
            ));
        }
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_record_field_inc_dec_statement_as_assignment() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("record field inc/dec skeleton");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected record field inc/dec assignment, got {skeleton:?}");
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_mutable_record_pointer_field_inc_dec_statement_as_assignment()
    {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("record arrow inc/dec skeleton");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected arrow field inc/dec assignment, got {skeleton:?}");
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_const_record_pointer_field_inc_dec_statement() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "const struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("const arrow inc/dec skeleton");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected const arrow field inc/dec to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("non-const record pointer variable"));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_record_field_inc_dec_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = inc_dec_for_step_skeleton_from_ast(&stmt).expect("record field for step");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected record field inc/dec for step to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("unsupported outside standalone statements"));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_record_pointer_field_inc_dec_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton =
            inc_dec_for_step_skeleton_from_ast(&stmt).expect("record pointer field for step");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected record pointer field inc/dec for step to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("unsupported outside standalone statements"));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_record_field_inc_dec_nested_base() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "MemberExpr",
                            "name": "inner",
                            "isArrow": false,
                            "type": { "qualType": "struct inner" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "struct outer" },
                                    "referencedDecl": { "name": "p" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("nested record field inc/dec");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected nested record field inc/dec to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("must have a direct record variable base"));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_compound_assignment_compute_type_mismatch() {
        let stmt = serde_json::json!({
            "kind": "CompoundAssignOperator",
            "opcode": "+=",
            "type": { "qualType": "unsigned char" },
            "computeLHSType": { "qualType": "int" },
            "computeResultType": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned char" },
                    "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "x"
                    }
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("compound assignment skeleton");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected compute-type mismatch to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("compound assignment integer promotion types are unsupported"));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_function_pointer_direct_call_expr() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (*)(int)" },
                            "referencedDecl": {
                                "kind": "ParmVarDecl",
                                "name": "fp"
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

        let skeleton = expr_skeleton_from_ast(&expr).expect("function pointer call skeleton");
        let lowered =
            lower_expr(&skeleton).expect("function pointer direct call should lower to IR call");

        let IrExpr::Call {
            callee, args, ty, ..
        } = lowered
        else {
            panic!("expected function pointer direct call IR, got {lowered:?}");
        };
        assert_eq!(callee, "fp");
        assert_eq!(ty.spelled, "int");
        assert_eq!(args.len(), 1);
        assert!(matches!(args[0], IrExpr::LValueToRValue { .. }));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_function_to_pointer_decay_as_explicit_ir() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "FunctionToPointerDecay",
            "type": { "qualType": "int (*)(int)" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int (int)" },
                    "referencedDecl": {
                        "kind": "FunctionDecl",
                        "name": "helper"
                    }
                }
            ]
        });

        let skeleton =
            expr_skeleton_from_ast(&expr).expect("function-to-pointer decay value skeleton");

        let lowered =
            lower_expr(&skeleton).expect("function-to-pointer decay should lower to explicit IR");
        let lowered_json =
            serde_json::to_value(&lowered).expect("serialize function-to-pointer decay IR");
        let Some(decay) = lowered_json.get("FunctionToPointerDecay") else {
            panic!("expected FunctionToPointerDecay IR node, got {lowered_json}");
        };
        assert_eq!(decay["target"]["spelled"], "int (*)(int)");
        assert_eq!(decay["expr"]["Var"]["name"], "helper");
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_call_expr_without_referenced_decl_kind() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (int)" },
                            "referencedDecl": {
                                "name": "helper"
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

        let skeleton = expr_skeleton_from_ast(&expr).expect("kindless call skeleton");
        assert!(matches!(
            skeleton,
            ClangExprSkeleton::Unsupported { ref node, .. } if node == "CallExpr"
        ));
        let error = lower_expr(&skeleton).expect_err("kindless callee must fail closed");
        assert!(error
            .message
            .contains("callee is not a direct function identifier"));
    }

    #[test]
    fn expr_skeleton_from_ast_maps_integer_conditional_operator() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "flag" }
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
                            "referencedDecl": { "name": "left" }
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
                            "referencedDecl": { "name": "right" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } = skeleton
        else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert_lvalue_to_rvalue_decl_ref(condition.as_ref(), "flag", true, 32);
        assert_lvalue_to_rvalue_decl_ref(then_expr.as_ref(), "left", true, 32);
        assert_lvalue_to_rvalue_decl_ref(else_expr.as_ref(), "right", true, 32);
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));

        let ir = lower_expr(&ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        })
        .expect("lower conditional skeleton");
        assert!(matches!(
            ir,
            IrExpr::Conditional {
                ty: IrType {
                    kind: IrTypeKind::Integer {
                        signed: true,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

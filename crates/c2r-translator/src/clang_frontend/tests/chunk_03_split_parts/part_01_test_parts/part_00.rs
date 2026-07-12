    #[test]
    fn expr_skeleton_from_ast_lowers_single_prefix_inc_dec_call_argument() {
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
                                "kind": "FunctionDecl",
                                "name": "helper"
                            }
                        }
                    ]
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Call { args, .. } = skeleton else {
            panic!("expected single prefix inc/dec call argument to lower, got {skeleton:?}");
        };
        let [ClangExprSkeleton::IncDec {
            target,
            prefix: true,
            ..
        }] = args.as_slice()
        else {
            panic!("expected one prefix inc/dec argument, got {args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_single_postfix_inc_dec_call_argument() {
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
                                "kind": "FunctionDecl",
                                "name": "helper"
                            }
                        }
                    ]
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Call { args, .. } = skeleton else {
            panic!("expected single postfix inc/dec call argument to lower, got {skeleton:?}");
        };
        let [ClangExprSkeleton::IncDec {
            target,
            prefix: false,
            ..
        }] = args.as_slice()
        else {
            panic!("expected one postfix inc/dec argument, got {args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_keeps_prefix_inc_dec_deref_operand_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "*",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("deref skeleton");

        let ClangExprSkeleton::Unsupported { reason, .. } = skeleton else {
            panic!("expected prefix inc/dec deref operand to fail closed, got {skeleton:?}");
        };
        assert!(
            reason.contains("deref pointer cannot use prefix increment/decrement value semantics"),
            "unexpected reason: {reason}"
        );
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_prefix_inc_dec_non_scalar_targets() {
        let cases = [
            (
                "prefix deref target",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "UnaryOperator",
                            "opcode": "*",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int *" },
                                    "referencedDecl": { "name": "p" }
                                }
                            ]
                        }
                    ]
                }),
                "simple variable",
            ),
            (
                "prefix pointer target",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }),
                "unsupported",
            ),
        ];

        for (label, stmt, expected_reason) in cases {
            let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect(label);

            let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
                panic!("expected unsupported {label}, got {skeleton:?}");
            };
            assert!(
                reason.contains(expected_reason),
                "unexpected reason for {label}: {reason}"
            );
        }
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_inc_dec_without_explicit_bool_postfix_flag() {
        let cases = [
            (
                "missing postfix flag",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }),
            ),
            (
                "string postfix flag",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": "false",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }),
            ),
        ];

        for (label, stmt) in cases {
            let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect(label);

            let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
                panic!("expected unsupported {label}, got {skeleton:?}");
            };
            assert!(
                reason.contains("explicit isPostfix flag"),
                "unexpected reason for {label}: {reason}"
            );
        }
    }

    #[test]
    fn type_from_qual_type_maps_fixed_width_integer_scalars() {
        let cases = [
            ("int8_t", "int8_t", true, 8),
            ("int16_t", "int16_t", true, 16),
            ("uint16_t", "uint16_t", false, 16),
            ("int32_t", "int32_t", true, 32),
            ("int64_t", "int64_t", true, 64),
            ("uint64_t", "uint64_t", false, 64),
        ];

        for (spelling, expected_canonical, expected_signed, expected_width) in cases {
            let ty = type_from_qual_type(spelling).expect("fixed-width integer type");

            assert_eq!(ty.spelled, spelling);
            assert_eq!(ty.canonical, expected_canonical);
            assert!(matches!(
                &ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if *signed == expected_signed && *width == expected_width
            ));
        }
    }

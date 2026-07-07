    #[test]
    fn stmt_skeleton_from_ast_preserves_if_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                integral_cast_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If { condition, .. } = skeleton else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_if_condition_integral_promotion() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                integral_promotion_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If { condition, .. } = skeleton else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert_signed_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_if_condition_non_integer_implicit_cast() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                floating_to_integral_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If { condition, .. } = &skeleton else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            condition,
            ClangExprSkeleton::Unsupported { node, reason }
                if node == "ImplicitCastExpr"
                    && reason.contains("FloatingToIntegral")
        ));
        let error =
            lower_stmt(&skeleton).expect_err("non-integer if condition cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_while_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "WhileStmt",
            "inner": [
                integral_cast_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = while_stmt_skeleton_from_ast(&stmt).expect("while skeleton");
        let ClangStmtSkeleton::While { condition, .. } = skeleton else {
            panic!("expected while skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_do_while_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "DoStmt",
            "inner": [
                return_one_stmt_ast(),
                integral_cast_condition_ast()
            ]
        });

        let skeleton = do_stmt_skeleton_from_ast(&stmt).expect("do-while skeleton");
        let ClangStmtSkeleton::DoWhile { condition, .. } = skeleton else {
            panic!("expected do-while skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_for_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "ForStmt",
            "inner": [
                {
                    "kind": "DeclStmt",
                    "inner": [
                        {
                            "kind": "VarDecl",
                            "name": "i",
                            "type": { "qualType": "int" },
                            "init": "c",
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                },
                {},
                integral_cast_condition_ast(),
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
                },
                return_one_stmt_ast()
            ]
        });

        let skeleton = for_stmt_skeleton_from_ast(&stmt).expect("for skeleton");
        let ClangStmtSkeleton::For {
            condition: Some(condition),
            ..
        } = skeleton
        else {
            panic!("expected for skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn while_stmt_skeleton_from_ast_maps_single_statement_body() {
        let stmt = serde_json::json!({
            "kind": "WhileStmt",
            "inner": [
                {
                    "kind": "BinaryOperator",
                    "opcode": ">",
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
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        },
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "0"
                        }
                    ]
                },
                {
                    "kind": "BinaryOperator",
                    "opcode": "=",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        },
                        {
                            "kind": "BinaryOperator",
                            "opcode": "+",
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
                                            "referencedDecl": { "name": "value" }
                                        }
                                    ]
                                },
                                {
                                    "kind": "UnaryOperator",
                                    "opcode": "~",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "0"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = while_stmt_skeleton_from_ast(&stmt).expect("while skeleton");
        let ClangStmtSkeleton::While { condition, body } = skeleton else {
            panic!("expected while skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            condition,
            ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Gt,
                ..
            }
        ));
        assert!(matches!(
            body.as_slice(),
            [ClangStmtSkeleton::Assign { .. }]
        ));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_accepts_prefix_increment_as_statement_step() {
        let stmt = serde_json::json!({
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
        });

        let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect("prefix increment step");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected assignment step, got {skeleton:?}");
        };
        assert!(matches!(target, ClangExprSkeleton::DeclRef { name, .. } if name == "i"));
        assert!(matches!(
            value,
            ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Add,
                ..
            }
        ));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_accepts_prefix_decrement_as_statement_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "--",
            "isPostfix": false,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "i" }
                }
            ]
        });

        let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect("prefix decrement step");

        let ClangStmtSkeleton::Assign { value, .. } = skeleton else {
            panic!("expected assignment step, got {skeleton:?}");
        };
        assert!(matches!(
            value,
            ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Sub,
                ..
            }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_value_position_prefix_inc_dec() {
        for (opcode, expected_op) in [
            ("++", ClangIncDecOperator::Inc),
            ("--", ClangIncDecOperator::Dec),
        ] {
            let expr = serde_json::json!({
                "kind": "UnaryOperator",
                "opcode": opcode,
                "isPostfix": false,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "int" },
                        "referencedDecl": { "name": "i" }
                    }
                ]
            });

            let skeleton = expr_skeleton_from_ast(&expr).expect("prefix inc/dec skeleton");

            let ClangExprSkeleton::IncDec {
                target,
                op,
                prefix: true,
                ty,
            } = skeleton
            else {
                panic!("expected prefix inc/dec skeleton for {opcode}, got {skeleton:?}");
            };
            assert_eq!(op, expected_op);
            assert_eq!(ty.spelled, "int");
            assert!(
                matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
                "unexpected target for {opcode}: {target:?}"
            );
        }
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_prefix_inc_dec_call_argument_with_independent_plain_arg() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int, int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (int, int)" },
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
                },
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "j" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Call { args, .. } = skeleton else {
            panic!("expected prefix inc/dec call argument with independent plain arg to lower, got {skeleton:?}");
        };
        let [
            ClangExprSkeleton::IncDec {
                target,
                prefix: true,
                ..
            },
            ClangExprSkeleton::DeclRef { name: plain_arg, .. },
        ] = args.as_slice()
        else {
            panic!("expected prefix inc/dec argument plus independent plain arg, got {args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
        assert_eq!(plain_arg, "j");
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_multiple_independent_prefix_inc_dec_call_arguments() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int, int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (int, int)" },
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
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "--",
                    "isPostfix": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "j" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Call { args, .. } = skeleton else {
            panic!("expected independent multiple prefix inc/dec call arguments to lower, got {skeleton:?}");
        };
        let [
            ClangExprSkeleton::IncDec {
                target: first_target,
                prefix: true,
                ..
            },
            ClangExprSkeleton::IncDec {
                target: second_target,
                prefix: true,
                ..
            },
        ] = args.as_slice()
        else {
            panic!("expected two prefix inc/dec arguments, got {args:?}");
        };
        assert!(
            matches!(first_target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected first target: {first_target:?}"
        );
        assert!(
            matches!(second_target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "j"),
            "unexpected second target: {second_target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_multiple_inc_dec_call_arguments_on_same_scalar() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int, int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (int, int)" },
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
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "--",
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

        let ClangExprSkeleton::Unsupported { reason, .. } = skeleton else {
            panic!("expected same-scalar multiple inc/dec call arguments to fail closed, got {skeleton:?}");
        };
        assert!(
            reason.contains("modify variable i more than once"),
            "unexpected reason: {reason}"
        );
    }

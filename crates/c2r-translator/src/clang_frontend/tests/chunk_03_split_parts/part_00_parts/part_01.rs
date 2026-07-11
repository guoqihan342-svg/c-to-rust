
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
    fn integer_decl_ref_ast(name: &str) -> Value {
        serde_json::json!({
            "kind": "DeclRefExpr",
            "type": { "qualType": "int" },
            "referencedDecl": { "name": name }
        })
    }

    fn integer_read_ast(name: &str) -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "int" },
            "inner": [integer_decl_ref_ast(name)]
        })
    }

    fn integer_literal_ast(value: u64) -> Value {
        serde_json::json!({
            "kind": "IntegerLiteral",
            "type": { "qualType": "int" },
            "value": value.to_string()
        })
    }

    fn integer_assignment_ast(name: &str, value: Value) -> Value {
        serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "=",
            "type": { "qualType": "int" },
            "inner": [integer_decl_ref_ast(name), value]
        })
    }

    fn comma_ast(lhs: Value, rhs: Value) -> Value {
        serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": ",",
            "type": { "qualType": "int" },
            "inner": [lhs, rhs]
        })
    }

    fn assignment_target_names(statements: &[ClangStmtSkeleton]) -> Vec<&str> {
        statements
            .iter()
            .map(|stmt| match stmt {
                ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef { name, .. },
                    ..
                } => name.as_str(),
                _ => panic!("expected direct assignment, got {stmt:?}"),
            })
            .collect()
    }

    fn unsupported_init_reason(statements: &[ClangStmtSkeleton]) -> &str {
        statements
            .iter()
            .find_map(|stmt| match stmt {
                ClangStmtSkeleton::Unsupported { reason } => Some(reason.as_str()),
                _ => None,
            })
            .expect("expected unsupported comma-chain leaf")
    }

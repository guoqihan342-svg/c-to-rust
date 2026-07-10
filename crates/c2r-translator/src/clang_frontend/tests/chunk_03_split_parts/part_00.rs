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
    fn for_init_comma_chain_lowers_two_assignments_in_sequence_point_order() {
        let init = comma_ast(
            integer_assignment_ast("i", integer_read_ast("start")),
            integer_assignment_ast("j", integer_read_ast("i")),
        );

        let statements =
            for_init_stmt_skeletons_from_ast(&init).expect("two-item comma init chain");

        assert_eq!(assignment_target_names(&statements), ["i", "j"]);
        let ClangStmtSkeleton::Assign { value, .. } = &statements[1] else {
            panic!("expected second assignment, got {:?}", statements[1]);
        };
        assert!(matches!(
            value,
            ClangExprSkeleton::LValueToRValue { expr, .. }
                if matches!(expr.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i")
        ));
    }

    #[test]
    fn for_init_comma_chain_flattens_three_item_left_associative_tree_in_order() {
        let init = comma_ast(
            comma_ast(
                integer_assignment_ast("i", integer_read_ast("start")),
                integer_assignment_ast("j", integer_read_ast("i")),
            ),
            integer_assignment_ast("k", integer_read_ast("j")),
        );

        let statements =
            for_init_stmt_skeletons_from_ast(&init).expect("three-item comma init chain");

        assert_eq!(assignment_target_names(&statements), ["i", "j", "k"]);
    }

    #[test]
    fn for_init_comma_chain_rejects_memory_assignment_target() {
        let memory_assignment = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "=",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "value",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct Holder" },
                            "referencedDecl": { "name": "holder" }
                        }
                    ]
                },
                integer_literal_ast(0)
            ]
        });
        let init = comma_ast(
            integer_assignment_ast("i", integer_literal_ast(0)),
            memory_assignment,
        );

        let statements = for_init_stmt_skeletons_from_ast(&init).expect("memory target refusal");

        assert!(unsupported_init_reason(&statements)
            .contains("target must be a direct integer scalar DeclRef"));
    }

    #[test]
    fn for_init_comma_chain_rejects_unsafe_assignment_shapes() {
        let decl_ref = |name: &str, qual_type: &str| {
            serde_json::json!({
                "kind": "DeclRefExpr",
                "type": { "qualType": qual_type },
                "referencedDecl": { "name": name }
            })
        };
        let assignment = |target: Value, value: Value| {
            serde_json::json!({
                "kind": "BinaryOperator",
                "opcode": "=",
                "type": { "qualType": "int" },
                "inner": [target, value]
            })
        };

        let cases: [(&str, Value, &[&str]); 5] = [
            (
                "direct pointer DeclRef target",
                assignment(decl_ref("ptr", "int *"), integer_literal_ast(0)),
                &["target", "integer scalar", "int *"],
            ),
            (
                "volatile integer target",
                assignment(
                    decl_ref("volatile_target", "volatile int"),
                    integer_literal_ast(0),
                ),
                &["target", "cannot be volatile", "volatile int"],
            ),
            (
                "volatile integer RHS read",
                assignment(
                    integer_decl_ref_ast("j"),
                    serde_json::json!({
                        "kind": "ImplicitCastExpr",
                        "castKind": "LValueToRValue",
                        "type": { "qualType": "int" },
                        "inner": [decl_ref("volatile_value", "volatile int")]
                    }),
                ),
                &["RHS", "read volatile type", "volatile int"],
            ),
            (
                "address-of RHS",
                assignment(
                    integer_decl_ref_ast("j"),
                    serde_json::json!({
                        "kind": "UnaryOperator",
                        "opcode": "&",
                        "type": { "qualType": "int *" },
                        "inner": [integer_decl_ref_ast("value")]
                    }),
                ),
                &["RHS", "address-of"],
            ),
            (
                "dereference target",
                assignment(
                    serde_json::json!({
                        "kind": "UnaryOperator",
                        "opcode": "*",
                        "type": { "qualType": "int" },
                        "inner": [decl_ref("ptr", "int *")]
                    }),
                    integer_literal_ast(0),
                ),
                &["target", "direct integer scalar DeclRef"],
            ),
        ];

        for (case, rejected_assignment, expected_reason_parts) in cases {
            let init = comma_ast(
                integer_assignment_ast("i", integer_literal_ast(0)),
                rejected_assignment,
            );
            let statements =
                for_init_stmt_skeletons_from_ast(&init).expect("comma-chain refusal skeleton");
            let [ClangStmtSkeleton::Assign { .. }, ClangStmtSkeleton::Unsupported { reason }] =
                statements.as_slice()
            else {
                panic!("{case}: expected Assign then Unsupported, got {statements:?}");
            };

            for expected in expected_reason_parts {
                assert!(
                    reason.contains(expected),
                    "{case}: expected reason fragment {expected:?}, got {reason:?}"
                );
            }
        }
    }

    #[test]
    fn for_init_comma_chain_rejects_call_and_deref_rhs() {
        let call = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(void)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (void)" },
                            "referencedDecl": { "kind": "FunctionDecl", "name": "next" }
                        }
                    ]
                }
            ]
        });
        let deref = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "*",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int *" },
                    "referencedDecl": { "name": "ptr" }
                }
            ]
        });

        for (rhs, expected_reason) in [(call, "call"), (deref, "dereference")] {
            let init = comma_ast(
                integer_assignment_ast("i", integer_literal_ast(0)),
                integer_assignment_ast("j", rhs),
            );
            let statements =
                for_init_stmt_skeletons_from_ast(&init).expect("RHS refusal skeleton");

            assert!(
                unsupported_init_reason(&statements).contains(expected_reason),
                "unexpected refusal for {expected_reason}: {}",
                unsupported_init_reason(&statements)
            );
        }
    }

    #[test]
    fn for_init_comma_chain_rejects_incdec_leaf() {
        let incdec = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [integer_decl_ref_ast("j")]
        });
        let init = comma_ast(
            integer_assignment_ast("i", integer_literal_ast(0)),
            incdec,
        );

        let statements = for_init_stmt_skeletons_from_ast(&init).expect("incdec leaf refusal");

        assert!(unsupported_init_reason(&statements)
            .contains("leaf must be a direct integer scalar assignment"));
    }

    #[test]
    fn for_condition_and_step_comma_operators_remain_unsupported() {
        let comma = comma_ast(integer_literal_ast(0), integer_literal_ast(1));

        let condition = condition_expr_skeleton_from_ast(&comma).expect("condition skeleton");
        assert!(matches!(
            condition,
            ClangExprSkeleton::Unsupported { node, reason }
                if node == "BinaryOperator" && reason.contains("opcode ,")
        ));

        let step = for_step_stmt_skeleton_from_ast(&comma).expect("step skeleton");
        assert!(matches!(
            step,
            ClangStmtSkeleton::Unsupported { reason }
                if reason.contains("ForStmt step BinaryOperator")
        ));
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

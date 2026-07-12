
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

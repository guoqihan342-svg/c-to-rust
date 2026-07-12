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

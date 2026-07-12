    #[test]
    fn expr_skeleton_from_ast_preserves_conditional_branch_integral_casts() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "uint32_t" },
                            "referencedDecl": { "name": "flag" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "uint32_t" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "2"
                        }
                    ]
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { else_expr, .. } = skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            else_expr.as_ref(),
            ClangExprSkeleton::Cast {
                implicit: true,
                target: ClangTypeSkeleton {
                    kind: ClangTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_conditional_condition_integral_cast() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                integral_cast_condition_ast(),
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "0"
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { condition, .. } = skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(*condition);
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_conditional_condition_integral_promotion() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                integral_promotion_condition_ast(),
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "0"
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { condition, .. } = skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert_signed_integral_condition_cast(*condition);
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_conditional_condition_non_integer_implicit_cast() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                floating_to_integral_condition_ast(),
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "0"
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { condition, .. } = &skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            condition.as_ref(),
            ClangExprSkeleton::Unsupported { node, reason }
                if node == "ImplicitCastExpr"
                    && reason.contains("FloatingToIntegral")
        ));
        let error = lower_expr(&skeleton).expect_err("non-integer condition cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_binary_conditional_operator() {
        let expr = serde_json::json!({
            "kind": "BinaryConditionalOperator",
            "type": { "qualType": "int" },
            "inner": []
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("binary conditional skeleton");

        assert!(matches!(
            skeleton,
            ClangExprSkeleton::Unsupported { ref node, ref reason }
                if node == "BinaryConditionalOperator"
                    && reason.contains("omitted-middle conditional")
        ));
        let error = lower_expr(&skeleton).expect_err("binary conditional must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("BinaryConditionalOperator"));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_integer_implicit_casts() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": ">",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "uint32_t" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "0"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("comparison skeleton");
        let ClangExprSkeleton::Binary { lhs, rhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::LValueToRValue {
            target: lhs_target,
            expr: lhs_expr,
        } = lhs.as_ref()
        else {
            panic!("expected preserved lhs LValueToRValue read, got {lhs:?}");
        };
        assert!(matches!(
            lhs_target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            lhs_expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = rhs.as_ref()
        else {
            panic!("expected preserved integral cast, got {rhs:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 0, .. }
        ));
    }

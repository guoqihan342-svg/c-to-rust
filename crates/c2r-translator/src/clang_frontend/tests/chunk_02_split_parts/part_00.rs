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

    #[test]
    fn expr_skeleton_from_ast_preserves_integer_noop_cast_in_value_context() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "+",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "NoOp",
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
                        }
                    ]
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("binary add skeleton");
        let ClangExprSkeleton::Binary { lhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = lhs.as_ref()
        else {
            panic!("expected preserved integer NoOp cast, got {lhs:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        let ClangExprSkeleton::LValueToRValue {
            target: read_target,
            expr: read_expr,
        } = expr.as_ref()
        else {
            panic!("expected preserved integer LValueToRValue read, got {expr:?}");
        };
        assert!(matches!(
            read_target.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            read_expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_array_to_pointer_decay_as_explicit_skeleton() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "ArrayToPointerDecay",
            "type": { "qualType": "int *" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int[4]" },
                    "referencedDecl": { "name": "table" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("array-to-pointer decay skeleton");

        let ClangExprSkeleton::ArrayToPointerDecay { target, expr } = &skeleton else {
            panic!("expected explicit array-to-pointer decay skeleton, got {skeleton:?}");
        };
        assert!(matches!(target.kind, ClangTypeKind::Pointer { .. }));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "table"
        ));
        let lowered = lower_expr(&skeleton).expect("array-to-pointer decay should lower to IR");
        let lowered_json =
            serde_json::to_value(&lowered).expect("serialize array-to-pointer decay IR");
        let Some(decay) = lowered_json.get("ArrayToPointerDecay") else {
            panic!("expected ArrayToPointerDecay IR node, got {lowered_json}");
        };
        assert_eq!(decay["target"]["spelled"], "int *");
        assert_eq!(decay["expr"]["Var"]["name"], "table");
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_array_to_pointer_decay_in_pointer_arithmetic_ir() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "+",
            "type": { "qualType": "int *" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "ArrayToPointerDecay",
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int[4]" },
                            "referencedDecl": { "name": "table" }
                        }
                    ]
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("array pointer arithmetic skeleton");

        let ClangExprSkeleton::Binary { lhs, rhs, .. } = &skeleton else {
            panic!("expected pointer arithmetic skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            lhs.as_ref(),
            ClangExprSkeleton::ArrayToPointerDecay { .. }
        ));
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
        let lowered = lower_expr(&skeleton)
            .expect("array decay pointer arithmetic should lower to explicit IR");
        let lowered_json =
            serde_json::to_value(&lowered).expect("serialize array decay pointer arithmetic IR");
        assert_eq!(
            lowered_json["Binary"]["lhs"]["ArrayToPointerDecay"]["expr"]["Var"]["name"],
            "table"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_integer_implicit_casts_for_bitwise_operands() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "&",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "uint32_t" },
                    "referencedDecl": { "name": "crc" }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "255"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("bitand skeleton");
        let ClangExprSkeleton::Binary { rhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = rhs.as_ref()
        else {
            panic!("expected preserved bitwise integral cast, got {rhs:?}");
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
            ClangExprSkeleton::IntegerLiteral { value: 255, .. }
        ));
    }

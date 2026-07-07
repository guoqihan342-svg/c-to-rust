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

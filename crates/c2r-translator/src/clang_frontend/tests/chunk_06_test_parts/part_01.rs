
    #[test]
    fn expr_skeleton_from_ast_lowers_single_chain_nested_direct_call_with_postfix_inc_dec_argument()
    {
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
                                "name": "outer"
                            }
                        }
                    ]
                },
                {
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
                                        "name": "middle"
                                    }
                                }
                            ]
                        },
                        {
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
                                                "name": "inner"
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
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("single-chain nested call skeleton");

        let ClangExprSkeleton::Call { callee, args, .. } = skeleton else {
            panic!("expected outer call to lower, got {skeleton:?}");
        };
        assert_eq!(callee, "outer");
        let [ClangExprSkeleton::Call {
            callee: middle_callee,
            args: middle_args,
            ..
        }] = args.as_slice()
        else {
            panic!("expected one middle call argument, got {args:?}");
        };
        assert_eq!(middle_callee, "middle");
        let [ClangExprSkeleton::Call {
            callee: inner_callee,
            args: inner_args,
            ..
        }] = middle_args.as_slice()
        else {
            panic!("expected one inner call argument, got {middle_args:?}");
        };
        assert_eq!(inner_callee, "inner");
        let [ClangExprSkeleton::IncDec {
            target,
            prefix: false,
            ..
        }] = inner_args.as_slice()
        else {
            panic!("expected one postfix inc/dec innermost argument, got {inner_args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_keeps_nested_side_effect_call_with_independent_plain_arg() {
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
                                "name": "outer"
                            }
                        }
                    ]
                },
                {
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
                                        "name": "inner"
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
                },
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "j" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Call { callee, args, .. } = skeleton else {
            panic!("expected nested side-effect call with independent plain arg to lower, got {skeleton:?}");
        };
        assert_eq!(callee, "outer");
        let [
            ClangExprSkeleton::Call {
                callee: inner_callee,
                args: inner_args,
                ..
            },
            ClangExprSkeleton::DeclRef { name: plain_arg, .. },
        ] = args.as_slice()
        else {
            panic!("expected inner call plus independent plain arg, got {args:?}");
        };
        assert_eq!(inner_callee, "inner");
        assert_eq!(plain_arg, "j");
        let [ClangExprSkeleton::IncDec { target, prefix: true, .. }] = inner_args.as_slice()
        else {
            panic!("expected one prefix inc/dec innermost argument, got {inner_args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_nested_side_effect_call_with_same_var_sibling_read() {
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
                                "name": "outer"
                            }
                        }
                    ]
                },
                {
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
                                        "name": "inner"
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
                },
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "i" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("call skeleton");

        let ClangExprSkeleton::Unsupported { reason, .. } = skeleton else {
            panic!("expected nested side-effect call with same-var sibling read to fail closed, got {skeleton:?}");
        };
        assert!(
            reason.contains("sibling argument reading modified variable i"),
            "unexpected reason: {reason}"
        );
    }

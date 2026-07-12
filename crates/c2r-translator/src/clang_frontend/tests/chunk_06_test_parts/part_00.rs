    #[test]
    fn expr_skeleton_from_ast_lowers_nested_direct_call_with_single_prefix_inc_dec_argument() {
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
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("nested call skeleton");

        let ClangExprSkeleton::Call { callee, args, .. } = skeleton else {
            panic!("expected outer call to lower, got {skeleton:?}");
        };
        assert_eq!(callee, "outer");
        let [ClangExprSkeleton::Call {
            callee: inner_callee,
            args: inner_args,
            ..
        }] = args.as_slice()
        else {
            panic!("expected one nested call argument, got {args:?}");
        };
        assert_eq!(inner_callee, "inner");
        let [ClangExprSkeleton::IncDec {
            target,
            prefix: true,
            ..
        }] = inner_args.as_slice()
        else {
            panic!("expected one prefix inc/dec inner argument, got {inner_args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_single_chain_nested_direct_call_with_prefix_inc_dec_argument() {
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
            prefix: true,
            ..
        }] = inner_args.as_slice()
        else {
            panic!("expected one prefix inc/dec innermost argument, got {inner_args:?}");
        };
        assert!(
            matches!(target.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "i"),
            "unexpected target: {target:?}"
        );
    }

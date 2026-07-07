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
    fn expr_skeleton_from_ast_keeps_nested_side_effect_call_with_plain_arg_fail_closed() {
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

        let ClangExprSkeleton::Unsupported { reason, .. } = skeleton else {
            panic!("expected nested side-effect call with plain arg to fail closed, got {skeleton:?}");
        };
        assert!(
            reason.contains(
                "side-effect nested call arguments cannot be combined with other call arguments"
            ),
            "unexpected reason: {reason}"
        );
    }

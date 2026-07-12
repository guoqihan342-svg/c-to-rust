    #[test]
    fn expr_skeleton_from_ast_preserves_integer_implicit_casts_for_bitwise_or_operands() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "|",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "uint32_t" },
                    "referencedDecl": { "name": "value" }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "3"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("bitor skeleton");
        let ClangExprSkeleton::Binary { rhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = rhs.as_ref()
        else {
            panic!("expected preserved bitwise-or integral cast, got {rhs:?}");
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
            ClangExprSkeleton::IntegerLiteral { value: 3, .. }
        ));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_maps_scalar_initializer() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "next",
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
                                    "referencedDecl": { "name": "crc" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            name,
            ty,
            init: Some(init),
        } = skeleton
        else {
            panic!("expected initialized decl skeleton, got {skeleton:?}");
        };
        assert_eq!(name, "next");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert_lvalue_to_rvalue_decl_ref(&init, "crc", false, 32);
    }

    #[test]
    fn compound_body_skeleton_from_ast_expands_multi_var_decl_stmt() {
        let body = serde_json::json!({
            "kind": "CompoundStmt",
            "inner": [
                {
                    "kind": "DeclStmt",
                    "inner": [
                        {
                            "kind": "VarDecl",
                            "name": "a",
                            "type": { "qualType": "int" },
                            "init": "c",
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "value": "1",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        },
                        {
                            "kind": "VarDecl",
                            "name": "b",
                            "type": { "qualType": "int" },
                            "init": "c",
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "value": "2",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "ReturnStmt",
                    "inner": [
                        {
                            "kind": "BinaryOperator",
                            "opcode": "+",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "kind": "VarDecl",
                                        "name": "a",
                                        "type": { "qualType": "int" }
                                    }
                                },
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "kind": "VarDecl",
                                        "name": "b",
                                        "type": { "qualType": "int" }
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = compound_body_skeleton_from_ast(&body).expect("compound body skeleton");
        let [ClangStmtSkeleton::Decl {
            name: a_name,
            init: Some(ClangExprSkeleton::IntegerLiteral { value: a_value, .. }),
            ..
        }, ClangStmtSkeleton::Decl {
            name: b_name,
            init: Some(ClangExprSkeleton::IntegerLiteral { value: b_value, .. }),
            ..
        }, ClangStmtSkeleton::Return { value: Some(_), .. }] = skeleton.as_slice()
        else {
            panic!("expected two declarations followed by return, got {skeleton:?}");
        };

        assert_eq!(a_name, "a");
        assert_eq!(*a_value, 1);
        assert_eq!(b_name, "b");
        assert_eq!(*b_value, 2);
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_maps_sparse_array_filler_initializer() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "type": { "qualType": "int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "int" }
                                },
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "int" }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "7"
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
            init: Some(ClangExprSkeleton::ArrayLiteral { elements, ty }),
            ..
        } = skeleton
        else {
            panic!("expected sparse array literal initializer, got {skeleton:?}");
        };
        assert_eq!(name, "table");
        assert!(matches!(ty.kind, ClangTypeKind::Array { len: Some(3), .. }));
        assert!(matches!(
            &elements[0],
            ClangExprSkeleton::IntegerLiteral { value: 0, .. }
        ));
        assert!(matches!(
            &elements[1],
            ClangExprSkeleton::IntegerLiteral { value: 7, .. }
        ));
        assert!(matches!(
            &elements[2],
            ClangExprSkeleton::IntegerLiteral { value: 0, .. }
        ));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_fixed_array_initializer_count_mismatch() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "type": { "qualType": "uint32_t[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "uint32_t[3]" },
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "1"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "2"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            init: Some(ClangExprSkeleton::Unsupported { node, reason, .. }),
            ..
        } = skeleton
        else {
            panic!("expected unsupported array initializer, got {skeleton:?}");
        };
        assert_eq!(node, "InitListExpr");
        assert!(reason.contains("initializer element count 2 does not match array length 3"));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_fixed_array_initializer_call_element() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "type": { "qualType": "uint32_t[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "uint32_t[3]" },
                            "inner": [
                                {
                                    "kind": "CallExpr",
                                    "type": { "qualType": "uint32_t" },
                                    "inner": [
                                        {
                                            "kind": "ImplicitCastExpr",
                                            "castKind": "FunctionToPointerDecay",
                                            "type": { "qualType": "uint32_t (*)(void)" },
                                            "inner": [
                                                {
                                                    "kind": "DeclRefExpr",
                                                    "type": { "qualType": "uint32_t (void)" },
                                                    "referencedDecl": {
                                                        "kind": "FunctionDecl",
                                                        "name": "helper"
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "3"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            init: Some(ClangExprSkeleton::Unsupported { node, reason, .. }),
            ..
        } = skeleton
        else {
            panic!("expected unsupported array initializer, got {skeleton:?}");
        };
        assert_eq!(node, "InitListExpr");
        assert!(reason.contains("initializer element 0"));
        assert!(reason.contains("only pure integer literal elements"));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_multiple_initializer_children() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "next",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "1"
                        },
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "2"
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected unsupported decl skeleton, got {skeleton:?}");
        };
        assert!(reason.contains("VarDecl with 2 initializer children"));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_init_marker_without_initializer_child() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "next",
                    "type": { "qualType": "uint32_t" },
                    "init": "c"
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected unsupported decl skeleton, got {skeleton:?}");
        };
        assert!(reason.contains("VarDecl initializer marker without initializer child"));
    }

    #[test]
    fn if_stmt_skeleton_from_ast_maps_single_statement_bodies() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
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
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "1"
                                }
                            ]
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

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } = skeleton
        else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert_lvalue_to_rvalue_decl_ref(&condition, "flag", true, 32);
        assert!(matches!(
            then_body.as_slice(),
            [ClangStmtSkeleton::Assign { .. }]
        ));
        assert!(matches!(
            else_body.as_slice(),
            [ClangStmtSkeleton::Assign { .. }]
        ));
    }

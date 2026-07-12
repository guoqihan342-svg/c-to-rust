
    #[test]
    fn decl_stmt_skeleton_from_ast_maps_fixed_array_initializer_list() {
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
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "IntegralCast",
                                    "type": { "qualType": "uint32_t" },
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "1"
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
            name,
            ty,
            init: Some(init),
        } = skeleton
        else {
            panic!("expected initialized array decl skeleton, got {skeleton:?}");
        };
        assert_eq!(name, "table");
        assert!(matches!(ty.kind, ClangTypeKind::Array { len: Some(3), .. }));
        let ClangExprSkeleton::ArrayLiteral { elements, ty } = init else {
            panic!("expected array literal initializer, got {init:?}");
        };
        assert!(matches!(ty.kind, ClangTypeKind::Array { len: Some(3), .. }));
        assert!(matches!(
            &elements[0],
            ClangExprSkeleton::Cast {
                target,
                expr,
                implicit: true
            } if matches!(
                target.kind,
                ClangTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ) && matches!(
                expr.as_ref(),
                ClangExprSkeleton::IntegerLiteral { value: 1, .. }
            )
        ));
        assert!(matches!(
            &elements[1],
            ClangExprSkeleton::IntegerLiteral { value: 2, .. }
        ));
        assert!(matches!(
            &elements[2],
            ClangExprSkeleton::IntegerLiteral { value: 3, .. }
        ));

        let ir = lower_expr(&ClangExprSkeleton::ArrayLiteral { elements, ty })
            .expect("lower array literal initializer");
        let IrExpr::ArrayLiteral { elements, .. } = ir else {
            panic!("expected lowered IR array literal, got {ir:?}");
        };
        assert!(matches!(
            &elements[0],
            IrExpr::Cast {
                target,
                expr,
                implicit: true,
                ..
            } if matches!(
                target.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ) && matches!(
                expr.as_ref(),
                IrExpr::LitInt { value: 1, .. }
            )
        ));
    }

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

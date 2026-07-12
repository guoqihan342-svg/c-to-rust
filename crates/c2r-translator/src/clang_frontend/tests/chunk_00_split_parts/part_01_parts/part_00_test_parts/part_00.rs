    #[test]
    fn stmt_skeleton_from_ast_preserves_assignment_rhs_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "=",
            "type": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned int" },
                    "referencedDecl": { "name": "value" }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "1"
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("assignment skeleton");
        let ir = lower_stmt(&skeleton).expect("lower assignment skeleton");

        let IrStmt::Assign { value, .. } = ir else {
            panic!("expected assignment, got {ir:?}");
        };
        assert!(matches!(
            value,
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
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
    fn stmt_skeleton_from_ast_preserves_decl_initializer_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "value",
                    "type": { "qualType": "unsigned int" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "IntegralCast",
                            "type": { "qualType": "unsigned int" },
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "1"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ir = lower_stmt(&skeleton).expect("lower decl skeleton");

        let IrStmt::Decl {
            init: Some(value), ..
        } = ir
        else {
            panic!("expected initialized decl, got {ir:?}");
        };
        assert!(matches!(
            value,
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
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
    fn stmt_skeleton_from_ast_preserves_return_value_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "ReturnStmt",
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "1"
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("return skeleton");
        let ir = lower_stmt(&skeleton).expect("lower return skeleton");

        let IrStmt::Return {
            value: Some(value), ..
        } = ir
        else {
            panic!("expected return value, got {ir:?}");
        };
        assert!(matches!(
            value,
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
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
    fn stmt_skeleton_from_ast_preserves_memset_local_array_decay_destination() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void *" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void *(*)(void *, int, uint64_t)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void *(void *, int, uint64_t)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "memset"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "BitCast",
                    "type": { "qualType": "void *" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "ArrayToPointerDecay",
                            "type": { "qualType": "unsigned char *" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "unsigned char[4]" },
                                    "referencedDecl": { "name": "table" }
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "7"
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "uint64_t" },
                    "value": "3"
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("memset call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower memset local array decay statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected memset call expression statement, got {ir:?}");
        };
        assert_eq!(callee, "memset");
        let [first, ..] = args.as_slice() else {
            panic!("expected memset arguments, got {args:?}");
        };
        assert!(matches!(
            first,
            IrExpr::ArrayToPointerDecay { expr, .. }
                if matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "table")
        ));
    }

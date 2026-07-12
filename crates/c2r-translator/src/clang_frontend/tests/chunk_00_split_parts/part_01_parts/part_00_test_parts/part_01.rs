
    #[test]
    fn stmt_skeleton_from_ast_preserves_memcpy_local_array_decay_arguments() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void *" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void *(*)(void *, const void *, uint64_t)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void *(void *, const void *, uint64_t)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "memcpy"
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
                                    "referencedDecl": { "name": "dst" }
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "BitCast",
                    "type": { "qualType": "const void *" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "ArrayToPointerDecay",
                            "type": { "qualType": "unsigned char *" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "unsigned char[4]" },
                                    "referencedDecl": { "name": "src" }
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "uint64_t" },
                    "value": "3"
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("memcpy call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower memcpy local array decay statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected memcpy call expression statement, got {ir:?}");
        };
        assert_eq!(callee, "memcpy");
        let [dest, src, ..] = args.as_slice() else {
            panic!("expected memcpy arguments, got {args:?}");
        };
        assert!(matches!(
            dest,
            IrExpr::ArrayToPointerDecay { expr, .. }
                if matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "dst")
        ));
        assert!(matches!(
            src,
            IrExpr::ArrayToPointerDecay { expr, .. }
                if matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "src")
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_signed_unary_minus() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "-",
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
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("unary minus skeleton");
        let ir = lower_expr(&skeleton).expect("lower unary minus skeleton");

        let IrExpr::Unary {
            op, operand, ty, ..
        } = ir
        else {
            panic!("expected IR unary minus, got {ir:?}");
        };
        assert_eq!(op, IrUnOp::Neg);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            operand.as_ref(),
            IrExpr::LValueToRValue { .. }
        ));
        assert_ir_lvalue_to_rvalue_var(operand.as_ref(), "value", true, 32);
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_non_integer_unary_plus() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "+",
            "type": { "qualType": "float" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "float" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("unary plus skeleton");

        let ClangExprSkeleton::Unsupported { node, reason } = skeleton else {
            panic!("expected non-integer unary plus to fail closed, got {skeleton:?}");
        };
        assert_eq!(node, "UnaryOperator");
        assert!(
            reason.contains("unary plus result type float is outside the integer promotion subset"),
            "{reason}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_logical_not() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "!",
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
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("logical not skeleton");
        let ir = lower_expr(&skeleton).expect("lower logical not skeleton");

        let IrExpr::Unary {
            op, operand, ty, ..
        } = ir
        else {
            panic!("expected IR logical not, got {ir:?}");
        };
        assert_eq!(op, IrUnOp::Not);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            operand.as_ref(),
            IrExpr::LValueToRValue { .. }
        ));
        assert_ir_lvalue_to_rvalue_var(operand.as_ref(), "value", true, 32);
    }

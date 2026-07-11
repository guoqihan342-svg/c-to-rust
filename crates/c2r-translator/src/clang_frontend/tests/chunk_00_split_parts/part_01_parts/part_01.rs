
    #[test]
    fn expr_skeleton_from_ast_lowers_bitwise_not_with_explicit_read() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "~",
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

        let skeleton = expr_skeleton_from_ast(&expr).expect("bitwise not skeleton");
        let ir = lower_expr(&skeleton).expect("lower bitwise not skeleton");

        let IrExpr::Unary {
            op, operand, ty, ..
        } = ir
        else {
            panic!("expected IR bitwise not, got {ir:?}");
        };
        assert_eq!(op, IrUnOp::BitNot);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(operand.as_ref(), "value", true, 32);
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_multiplicative_integral_cast_operands() {
        for (opcode, expected_op) in [
            ("*", IrBinOp::Mul),
            ("/", IrBinOp::Div),
            ("%", IrBinOp::Mod),
        ] {
            let expr = serde_json::json!({
                "kind": "BinaryOperator",
                "opcode": opcode,
                "type": { "qualType": "unsigned int" },
                "inner": [
                    {
                        "kind": "ImplicitCastExpr",
                        "castKind": "LValueToRValue",
                        "type": { "qualType": "unsigned int" },
                        "inner": [
                            {
                                "kind": "DeclRefExpr",
                                "type": { "qualType": "unsigned int" },
                                "referencedDecl": { "name": "value" }
                            }
                        ]
                    },
                    {
                        "kind": "ImplicitCastExpr",
                        "castKind": "IntegralCast",
                        "type": { "qualType": "unsigned int" },
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

            let skeleton = expr_skeleton_from_ast(&expr)
                .unwrap_or_else(|_| panic!("multiplicative skeleton for {opcode}"));
            let ir = lower_expr(&skeleton)
                .unwrap_or_else(|_| panic!("lower multiplicative skeleton for {opcode}"));

            let IrExpr::Binary {
                op, lhs, rhs, ty, ..
            } = ir
            else {
                panic!("expected IR multiplicative op for {opcode}, got {ir:?}");
            };
            assert_eq!(op, expected_op);
            assert!(matches!(
                ty.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ));
            assert_ir_lvalue_to_rvalue_var(lhs.as_ref(), "value", false, 32);
            assert!(matches!(
                rhs.as_ref(),
                IrExpr::Cast { target, .. }
                    if matches!(
                        target.kind,
                        IrTypeKind::Integer {
                            signed: false,
                            width: 32
                        }
                    )
            ));
        }
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_direct_call_expr() {
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

        let skeleton = expr_skeleton_from_ast(&expr).expect("direct call skeleton");
        let ir = lower_expr(&skeleton).expect("lower direct call skeleton");

        let IrExpr::Call {
            callee, args, ty, ..
        } = ir
        else {
            panic!("expected IR call, got {ir:?}");
        };
        assert_eq!(callee, "helper");
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        let [arg] = args.as_slice() else {
            panic!("expected one direct call argument, got {args:?}");
        };
        assert_ir_lvalue_to_rvalue_var(arg, "value", true, 32);
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_string_literal_as_array_decay_call_arg() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void (*)(const char *)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (const char *)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "observe"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "ArrayToPointerDecay",
                    "type": { "qualType": "char *" },
                    "inner": [
                        {
                            "kind": "StringLiteral",
                            "type": { "qualType": "char[4]" },
                            "value": "\"kv\\n\""
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("string literal call skeleton");
        let ClangExprSkeleton::Call { args, .. } = skeleton else {
            panic!("expected call skeleton, got {skeleton:?}");
        };
        let [ClangExprSkeleton::ArrayToPointerDecay { expr, .. }] = args.as_slice() else {
            panic!("expected string literal array decay arg, got {args:?}");
        };
        let ClangExprSkeleton::ArrayLiteral { elements, ty } = expr.as_ref() else {
            panic!("expected string literal to lower as byte array literal, got {expr:?}");
        };
        let values: Vec<u64> = elements
            .iter()
            .map(|element| match element {
                ClangExprSkeleton::IntegerLiteral { value, .. } => *value,
                other => panic!("expected byte literal element, got {other:?}"),
            })
            .collect();

        assert_eq!(values, vec![107, 118, 10, 0]);
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Array { len: Some(4), .. }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_array_subscript_index_integer_read() {
        let expr = serde_json::json!({
            "kind": "ArraySubscriptExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "ArrayToPointerDecay",
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int[3]" },
                            "referencedDecl": { "name": "table" }
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
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("array subscript skeleton");
        let ir = lower_expr(&skeleton).expect("lower array subscript skeleton");

        let IrExpr::Index {
            base, index, ty, ..
        } = ir
        else {
            panic!("expected IR array index, got {ir:?}");
        };
        assert!(matches!(
            base.as_ref(),
            IrExpr::Var { name, .. } if name == "table"
        ));
        assert_ir_lvalue_to_rvalue_var(index.as_ref(), "i", true, 32);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_record_address_of() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "&",
            "type": { "qualType": "struct fdb_blob *" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "struct fdb_blob" },
                    "referencedDecl": { "name": "blob" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("address-of skeleton");
        let ClangExprSkeleton::AddrOf { operand, ty } = &skeleton else {
            panic!("expected address-of skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "blob"
        ));
        assert!(matches!(ty.kind, ClangTypeKind::Pointer { .. }));

        let ir = lower_expr(&skeleton).expect("lower address-of skeleton");
        let IrExpr::AddrOf { operand, ty, .. } = ir else {
            panic!("expected IR address-of expression, got {ir:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == "blob"
        ));
        let IrTypeKind::Pointer { pointee } = ty.kind else {
            panic!("expected address-of pointer type, got {ty:?}");
        };
        assert!(matches!(
            &pointee.kind,
            IrTypeKind::Record { name, .. } if name == "fdb_blob"
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_direct_call_with_record_address_arg() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(struct fdb_blob *)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (struct fdb_blob *)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "consume_blob"
                            }
                        }
                    ]
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "&",
                    "type": { "qualType": "struct fdb_blob *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct fdb_blob" },
                            "referencedDecl": { "name": "blob" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("direct address call skeleton");
        let ClangExprSkeleton::Call { callee, args, .. } = &skeleton else {
            panic!("expected direct call skeleton, got {skeleton:?}");
        };
        assert_eq!(callee, "consume_blob");
        let [ClangExprSkeleton::AddrOf { operand, .. }] = args.as_slice() else {
            panic!("expected address-of call arg, got {args:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "blob"
        ));

        let ir = lower_expr(&skeleton).expect("lower direct address call skeleton");
        let IrExpr::Call { callee, args, .. } = ir else {
            panic!("expected IR direct call, got {ir:?}");
        };
        assert_eq!(callee, "consume_blob");
        let [IrExpr::AddrOf { operand, .. }] = args.as_slice() else {
            panic!("expected IR address-of call arg, got {args:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == "blob"
        ));
    }

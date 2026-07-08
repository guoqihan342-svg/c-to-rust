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

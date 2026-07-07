    fn integral_cast_condition_ast() -> Value {
        serde_json::json!({
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
        })
    }

    fn integral_promotion_condition_ast() -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "IntegralPromotion",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "signed char" },
                    "referencedDecl": { "name": "small" }
                }
            ]
        })
    }

    fn floating_to_integral_condition_ast() -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "FloatingToIntegral",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "float" },
                    "referencedDecl": { "name": "flag" }
                }
            ]
        })
    }

    fn return_one_stmt_ast() -> Value {
        serde_json::json!({
            "kind": "ReturnStmt",
            "inner": [
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        })
    }

    #[test]
    fn clang_source_range_summary_falls_back_to_loc_when_range_is_missing() {
        let node = serde_json::json!({
            "kind": "GotoStmt",
            "loc": { "line": 20, "col": 7 }
        });

        assert_eq!(
            clang_source_range_summary(&node),
            Some("20:7-20:7".to_string())
        );
    }

    fn assert_unsigned_integral_condition_cast(condition: ClangExprSkeleton) {
        assert!(matches!(
            condition,
            ClangExprSkeleton::Cast {
                implicit: true,
                target: ClangTypeSkeleton {
                    kind: ClangTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    fn assert_signed_integral_condition_cast(condition: ClangExprSkeleton) {
        assert!(matches!(
            condition,
            ClangExprSkeleton::Cast {
                implicit: true,
                target: ClangTypeSkeleton {
                    kind: ClangTypeKind::Integer {
                        signed: true,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    fn assert_lvalue_to_rvalue_decl_ref(
        expr: &ClangExprSkeleton,
        expected_name: &str,
        signed: bool,
        width: u16,
    ) {
        let ClangExprSkeleton::LValueToRValue {
            target,
            expr: operand,
        } = expr
        else {
            panic!("expected LValueToRValue read of {expected_name}, got {expr:?}");
        };
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: actual_signed,
                width: actual_width
            } if actual_signed == signed && actual_width == width
        ));
        assert!(matches!(
            operand.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == expected_name
        ));
    }

    fn assert_ir_lvalue_to_rvalue_var(
        expr: &IrExpr,
        expected_name: &str,
        signed: bool,
        width: u16,
    ) {
        let IrExpr::LValueToRValue {
            target,
            expr: operand,
            ..
        } = expr
        else {
            panic!("expected LValueToRValue read of {expected_name}, got {expr:?}");
        };
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: actual_signed,
                width: actual_width
            } if actual_signed == signed && actual_width == width
        ));
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == expected_name
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_maps_comparison_opcodes() {
        let cases = [
            ("==", ClangBinaryOperator::Eq),
            ("!=", ClangBinaryOperator::Neq),
            ("<", ClangBinaryOperator::Lt),
            ("<=", ClangBinaryOperator::Le),
            (">", ClangBinaryOperator::Gt),
            (">=", ClangBinaryOperator::Ge),
        ];

        for (opcode, expected) in cases {
            let expr = serde_json::json!({
                "kind": "BinaryOperator",
                "opcode": opcode,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "int" },
                        "referencedDecl": { "name": "value" }
                    },
                    {
                        "kind": "IntegerLiteral",
                        "type": { "qualType": "int" },
                        "value": "0"
                    }
                ]
            });

            let skeleton = expr_skeleton_from_ast(&expr).expect("comparison skeleton");
            let ClangExprSkeleton::Binary { op, .. } = skeleton else {
                panic!("expected binary skeleton for {opcode}, got {skeleton:?}");
            };
            assert_eq!(op, expected);
        }
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_null_to_pointer_comparison() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "!=",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "const int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "const int *" },
                            "referencedDecl": { "name": "values" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "NullToPointer",
                    "type": { "qualType": "const int *" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "0"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("null pointer comparison skeleton");
        let ir = lower_expr(&skeleton).expect("lower null pointer comparison skeleton");

        let IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } = ir
        else {
            panic!("expected IR comparison, got {ir:?}");
        };
        assert_eq!(op, IrBinOp::Neq);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            lhs.as_ref(),
            IrExpr::Var { name, .. } if name == "values"
        ));
        assert!(matches!(
            rhs.as_ref(),
            IrExpr::NullPtr { ty, .. } if matches!(ty.kind, IrTypeKind::Pointer { .. })
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_maps_bitwise_or_and_left_shift_opcodes() {
        let cases = [
            ("|", ClangBinaryOperator::BitOr),
            ("<<", ClangBinaryOperator::Shl),
        ];

        for (opcode, expected) in cases {
            let expr = serde_json::json!({
                "kind": "BinaryOperator",
                "opcode": opcode,
                "type": { "qualType": "unsigned int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "unsigned int" },
                        "referencedDecl": { "name": "value" }
                    },
                    {
                        "kind": "IntegerLiteral",
                        "type": { "qualType": "unsigned int" },
                        "value": "4"
                    }
                ]
            });

            let skeleton = expr_skeleton_from_ast(&expr).expect("bitwise skeleton");
            let ClangExprSkeleton::Binary { op, .. } = skeleton else {
                panic!("expected binary skeleton for {opcode}, got {skeleton:?}");
            };
            assert_eq!(op, expected);
        }
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_subtraction_integral_cast_operands() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "-",
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
                            "value": "1"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("subtraction skeleton");
        let ir = lower_expr(&skeleton).expect("lower subtraction skeleton");

        let IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } = ir
        else {
            panic!("expected IR subtraction, got {ir:?}");
        };
        assert_eq!(op, IrBinOp::Sub);
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

    #[test]
    fn implicit_cast_with_unmodeled_cast_kind_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "FloatingToIntegral",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "float" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("unmodeled implicit cast should parse as unsupported skeleton");
        let ClangExprSkeleton::Unsupported { node, reason } = &skeleton else {
            panic!("expected unsupported skeleton, got {skeleton:?}");
        };
        assert_eq!(node, "ImplicitCastExpr");
        assert!(reason.contains("FloatingToIntegral"), "{reason}");

        let error = lower_expr(&skeleton).expect_err("unsupported implicit cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("FloatingToIntegral"), "{error:?}");
    }

    #[test]
    fn implicit_cast_with_integral_to_floating_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "IntegralToFloating",
            "type": { "qualType": "float" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("non-integral implicit cast should parse as unsupported skeleton");
        let ClangExprSkeleton::Unsupported { node, reason } = &skeleton else {
            panic!("expected unsupported skeleton, got {skeleton:?}");
        };
        assert_eq!(node, "ImplicitCastExpr");
        assert!(reason.contains("IntegralToFloating"), "{reason}");

        let error = lower_expr(&skeleton).expect_err("unsupported implicit cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("IntegralToFloating"), "{error:?}");
    }

    #[test]
    fn implicit_cast_without_cast_kind_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("implicit cast without castKind should parse as unsupported skeleton");
        let ClangExprSkeleton::Unsupported { node, reason } = &skeleton else {
            panic!("expected unsupported skeleton, got {skeleton:?}");
        };
        assert_eq!(node, "ImplicitCastExpr");
        assert!(reason.contains("missing castKind"), "{reason}");

        let error = lower_expr(&skeleton).expect_err("unsupported implicit cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("missing castKind"), "{error:?}");
    }

    #[test]
    fn implicit_cast_noop_preserves_operand() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "NoOp",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("NoOp cast should preserve operand");
        assert!(matches!(
            skeleton,
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
    }

    #[test]
    fn c_style_noop_integer_cast_preserves_explicit_cast_node() {
        let expr = serde_json::json!({
            "kind": "CStyleCastExpr",
            "castKind": "NoOp",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "uint32_t" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("C-style NoOp cast skeleton");
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = &skeleton
        else {
            panic!("expected explicit C-style NoOp cast, got {skeleton:?}");
        };

        assert!(!implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
    }

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
            IrExpr::Var { name, .. } if name == "value"
        ));
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
            IrExpr::Var { name, .. } if name == "value"
        ));
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

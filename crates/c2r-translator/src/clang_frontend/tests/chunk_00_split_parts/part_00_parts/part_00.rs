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

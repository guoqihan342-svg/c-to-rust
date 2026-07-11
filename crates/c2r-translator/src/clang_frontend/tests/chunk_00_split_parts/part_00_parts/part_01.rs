
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
    fn implicit_integer_noop_cast_stays_explicit_without_value_context() {
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

        let skeleton = expr_skeleton_from_ast(&expr).expect("NoOp cast should stay explicit");
        let ir = lower_expr(&skeleton).expect("lower explicit integer NoOp cast");

        let IrExpr::Cast {
            target,
            expr,
            implicit,
            ..
        } = ir
        else {
            panic!("expected explicit integer NoOp cast, got {ir:?}");
        };
        assert!(implicit);
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            expr.as_ref(),
            IrExpr::Var { name, .. } if name == "value"
        ));
    }

    #[test]
    fn implicit_integer_noop_cast_preserves_inner_lvalue_to_rvalue_without_value_context() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "NoOp",
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

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("NoOp cast should preserve inner LValueToRValue");
        let ir = lower_expr(&skeleton).expect("lower explicit integer NoOp cast");

        let IrExpr::Cast { expr, implicit, .. } = ir else {
            panic!("expected explicit integer NoOp cast, got {ir:?}");
        };
        assert!(implicit);
        assert_ir_lvalue_to_rvalue_var(expr.as_ref(), "value", true, 32);
    }

    #[test]
    fn value_expr_skeleton_preserves_target_dependent_integer_lvalue_to_rvalue_for_abi_binding() {
        for (target_spelling, operand_spelling) in [
            ("unsigned long", "unsigned long"),
            ("size_t", "size_t"),
            ("unsigned long", "const unsigned long"),
        ] {
            let expr = serde_json::json!({
                "kind": "ImplicitCastExpr",
                "castKind": "LValueToRValue",
                "type": { "qualType": target_spelling },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": operand_spelling },
                        "referencedDecl": { "name": "value" }
                    }
                ]
            });

            let skeleton = value_expr_skeleton_from_ast(&expr)
                .unwrap_or_else(|_| {
                    panic!(
                        "target-dependent integer read skeleton for {target_spelling} from {operand_spelling}"
                    )
                });
            let ClangExprSkeleton::LValueToRValue {
                target,
                expr: operand,
            } = &skeleton
            else {
                panic!("expected target-dependent integer LValueToRValue read for {target_spelling} from {operand_spelling}, got {skeleton:?}");
            };
            assert_eq!(target.spelled, target_spelling);
            assert!(matches!(
                target.kind,
                ClangTypeKind::Unsupported { ref reason }
                    if reason.contains("requires target ABI width provenance")
            ));
            assert!(matches!(
                operand.as_ref(),
                ClangExprSkeleton::DeclRef { name, .. } if name == "value"
            ));
        }
    }

    #[test]
    fn value_expr_skeleton_keeps_pointer_lvalue_to_rvalue_transparent() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "unsigned long *" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned long *" },
                    "referencedDecl": { "name": "p" }
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr)
            .expect("pointer LValueToRValue should stay transparent");

        assert!(matches!(
            skeleton,
            ClangExprSkeleton::DeclRef { ref name, .. } if name == "p"
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
    fn c_style_integral_cast_preserves_inner_lvalue_to_rvalue_without_value_context() {
        let expr = serde_json::json!({
            "kind": "CStyleCastExpr",
            "castKind": "IntegralCast",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "uint64_t" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "uint64_t" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("C-style integral cast should preserve inner LValueToRValue");
        let ir = lower_expr(&skeleton).expect("lower explicit C-style integral cast");

        let IrExpr::Cast {
            target,
            expr,
            implicit,
            ..
        } = ir
        else {
            panic!("expected explicit C-style integral cast, got {ir:?}");
        };
        assert!(!implicit);
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(expr.as_ref(), "value", false, 64);
    }

    #[test]
    fn c_style_noop_integer_cast_preserves_inner_lvalue_to_rvalue_without_value_context() {
        let expr = serde_json::json!({
            "kind": "CStyleCastExpr",
            "castKind": "NoOp",
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
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("C-style integer NoOp cast should preserve inner LValueToRValue");
        let ir = lower_expr(&skeleton).expect("lower explicit C-style integer NoOp cast");

        let IrExpr::Cast {
            target,
            expr,
            implicit,
            ..
        } = ir
        else {
            panic!("expected explicit C-style integer NoOp cast, got {ir:?}");
        };
        assert!(!implicit);
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(expr.as_ref(), "value", false, 32);
    }

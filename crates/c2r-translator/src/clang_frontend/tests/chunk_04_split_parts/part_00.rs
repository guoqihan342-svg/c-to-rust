    #[test]
    fn sizeof_integer_type_lowers_to_profile_bound_size_t_literal() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof integer skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof integer should lower");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert_eq!(ty.spelled, "size_t");
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));
    }

    #[test]
    fn sizeof_int_lowers_from_target_int_width_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(int) should lower with ABI profile");

        let IrExpr::LitInt { value, .. } = ir else {
            panic!("expected sizeof(int) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 2);
    }

    #[test]
    fn sizeof_size_t_lowers_from_target_pointer_width_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "size_t"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof size_t skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof size_t should lower");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(size_t) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 8);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn type_from_qual_type_binds_double_underscore_size_t_with_target_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-pc-windows-msvc".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        let ty = type_from_qual_type_with_target_abi("__size_t", Some(&abi))
            .expect("__size_t should parse with target ABI profile");
        assert_eq!(ty.spelled, "__size_t");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));

        let unbound = type_from_qual_type("__size_t").expect("__size_t should parse as unbound");
        assert!(matches!(unbound.kind, ClangTypeKind::Unsupported { .. }));
    }

    #[test]
    fn sizeof_pointer_type_lowers_from_target_pointer_width_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "const int *"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof pointer skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof pointer should lower with ABI profile");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(pointer) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 8);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_pointer_type_stays_fail_closed_without_pointer_width_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "const int *"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof pointer skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof pointer requires target profile");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("pointer-width provenance"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_long_lowers_from_target_long_width_profile() {
        for (abi_name, long_width, expected_size) in [
            ("x86_64-unknown-linux-gnu", 64, 8),
            ("x86_64-pc-windows-msvc", 32, 4),
        ] {
            let abi = TargetAbiProfile {
                triple_or_abi: abi_name.to_string(),
                endianness: Some("little".to_string()),
                int_width: 32,
                char_width: 8,
                plain_char_signed: Some(true),
                short_width: 16,
                long_width,
                long_long_width: 64,
                pointer_width: 64,
                ..TargetAbiProfile::default()
            };
            let expr = serde_json::json!({
                "kind": "UnaryExprOrTypeTraitExpr",
                "type": {"qualType": "size_t"},
                "valueCategory": "prvalue",
                "name": "sizeof",
                "argType": {"qualType": "long"}
            });

            let mut skeleton =
                expr_skeleton_from_ast(&expr).expect("sizeof(long) skeleton should parse");
            bind_target_abi_to_expr(&mut skeleton, &abi);
            let ir = lower_expr(&skeleton).expect("sizeof(long) should lower with ABI profile");

            let IrExpr::LitInt { value, ty, .. } = ir else {
                panic!("expected sizeof(long) to lower to LitInt, got {ir:?}");
            };
            assert_eq!(value, expected_size, "{abi_name}");
            assert_eq!(ty.spelled, "size_t");
        }
    }

    #[test]
    fn sizeof_fixed_integer_array_type_lowers_to_total_byte_size() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[3]"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int[3]) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(int[3]) should lower with ABI profile");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(int[3]) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 6);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_incomplete_array_type_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[]"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof(int[]) skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof incomplete array must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("complete array bound"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_vla_like_array_type_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[n]"}
        });

        let error = expr_skeleton_from_ast(&expr).expect_err("VLA-like sizeof must fail closed");

        assert_eq!(error.kind, "invalid_array_type");
        assert!(
            error.message.contains("array length is not usize"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_array_result_exceeding_target_size_t_stays_fail_closed() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-size-t-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 16,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[40000]"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int[40000]) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let error = lower_expr(&skeleton).expect_err("oversized sizeof result must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("does not fit target result type"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_target_dependent_integer_stays_fail_closed_without_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "long"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof(long) skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof(long) without ABI must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error
                .message
                .contains("requires target ABI width provenance"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_expression_operand_stays_fail_closed_without_arg_type() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "referencedDecl": {
                        "kind": "VarDecl",
                        "name": "value"
                    },
                    "type": {"qualType": "int"}
                }
            ]
        });

        let error =
            expr_skeleton_from_ast(&expr).expect_err("sizeof expression operand must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_operand");
        assert!(
            error.message.contains("expression operand"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_expression_operand_lowers_with_arg_type_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"},
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "referencedDecl": {
                        "kind": "VarDecl",
                        "name": "value"
                    },
                    "type": {"qualType": "int"}
                }
            ]
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof expression argType should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(value) should lower through argType");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(value) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_record_type_stays_fail_closed_without_layout_provenance() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "struct point"}
        });

        let error = expr_skeleton_from_ast(&expr).expect_err("record sizeof must fail closed");

        assert!(
            error.message.contains("sizeof") && error.message.contains("layout"),
            "unexpected error: {error:?}"
        );
    }

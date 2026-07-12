
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
    fn sizeof_expression_operand_derives_type_without_arg_type() {
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

        let mut skeleton = expr_skeleton_from_ast(&expr)
            .expect("sizeof expression should derive the unique operand type");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("derived int operand type should lower");

        let IrExpr::LitInt { value, .. } = ir else {
            panic!("expected derived sizeof(value) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 4);
    }

    #[test]
    fn sizeof_expression_operand_without_type_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "inner": [{"kind": "DeclRefExpr"}]
        });

        let error = expr_skeleton_from_ast(&expr)
            .expect_err("sizeof expression without operand type must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_operand");
        assert!(error.message.contains("missing type.qualType"));
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

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("record sizeof must survive until layout binding");
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            int_width: 32,
            char_width: 8,
            long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let error = lower_expr(&skeleton).expect_err("record sizeof must fail without layout");

        assert!(
            error.message.contains("sizeof") && error.message.contains("layout"),
            "unexpected error: {error:?}"
        );
    }

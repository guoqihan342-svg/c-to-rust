    #[test]
    fn translates_for_loop_by_lowering_to_bounded_while() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-for".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_for".to_string(),
        c_source: "int sum_for(int limit) { int total = 0; for (int i = 0; i < limit; i++) { total = total + i; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("let mut i: i32 = 0;"));
        assert!(result.rust_code.contains("while i < limit {"));
        assert!(result.rust_code.contains("i += 1;"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"for".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"structured-for".to_string()));
    }

    #[test]
    fn translates_for_loop_with_compound_assignment_step() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-for-compound-step".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_for_compound_step".to_string(),
        c_source: "int sum_for_compound_step(int limit) { int total = 0; for (int i = 0; i < limit; i += 1) { total = total + i; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("while i < limit {"));
        assert!(result.rust_code.contains("i += 1;"));
    }

    #[test]
    fn translates_simple_call_expression_and_records_call_rule() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "call_hook".to_string(),
            c_source: "int call_hook(int value) { observe(value); return value; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("observe(value);"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"simple_call".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"simple-call".to_string()));
    }

    #[test]
    fn translates_direct_call_expressions_and_records_callee_evidence() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "call-expression".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "call_expression".to_string(),
        c_source: "int call_expression(int value) { int first = helper(value); value = helper(first); return helper(value); }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("let mut first: i32 = helper(value);"));
        assert!(result.rust_code.contains("value = helper(first);"));
        assert!(result.rust_code.contains("return helper(value);"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"call_expression".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));

        let plan = serde_json::to_value(&result.plan).unwrap();
        let calls = plan["call_expressions"].as_array().unwrap();
        assert_eq!(calls.len(), 3);
        assert_eq!(calls[0]["callee"], "helper");
        assert_eq!(calls[0]["arguments"], serde_json::json!(["value"]));
        assert_eq!(calls[1]["source_expression"], "helper(first)");
        assert_eq!(calls[2]["statement_context"], "return");
    }

    #[test]
    fn translates_compound_assignment_statement_and_records_rule() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "compound-assignment".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "compound_assignment".to_string(),
        c_source:
            "int compound_assignment(int value) { value += 1; value-=1; value *= 2; return value; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn compound_assignment(mut value: i32) -> i32"));
        assert!(result.rust_code.contains("value += 1;"));
        assert!(result.rust_code.contains("value -= 1;"));
        assert!(result.rust_code.contains("value *= 2;"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"compound_assignment".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"compound-assignment".to_string()));
    }

    #[test]
    fn translates_increment_and_decrement_statements_and_records_rule() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "inc-dec".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "inc_dec".to_string(),
            c_source:
                "int inc_dec(int value) { value++; --value; ++value; value--; return value; }"
                    .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn inc_dec(mut value: i32) -> i32"));
        assert_eq!(result.rust_code.matches("value += 1;").count(), 2);
        assert_eq!(result.rust_code.matches("value -= 1;").count(), 2);
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"inc_dec".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"increment-decrement".to_string()));
    }

    #[test]
    fn legacy_translation_rejects_leading_zero_octal_integer_literals() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "octal-literal-reject".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_octal".to_string(),
            c_source: "int add_octal(int value) { int base = 010; return value + base; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_syntax"
                    && error.message.contains("leading-zero integer literal")),
            "{:?}",
            result.errors
        );
        assert!(!result.rust_code.contains("010"));
    }

    #[test]
    fn legacy_translation_rejects_leading_zero_octal_literal_in_return_expression() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "octal-return-reject".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "permission_bits".to_string(),
            c_source: "int permission_bits(int value) { return value + 0644; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_syntax"
                    && error.message.contains("leading-zero integer literal")),
            "{:?}",
            result.errors
        );
    }

    #[test]
    fn legacy_translation_accepts_hex_and_plain_zero_literals() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "hex-zero-accept".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "mask_low_bits".to_string(),
        c_source: "int mask_low_bits(int value) { int mask = 0xFF; if (value == 0) { return 0; } return value & mask; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(
            !result
                .errors
                .iter()
                .any(|error| error.message.contains("leading-zero integer literal")),
            "{:?}",
            result.errors
        );
    }

    #[test]
    fn legacy_translation_rejects_bare_char_type_as_type_uncertainty() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "bare-char-reject".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "is_negative_char".to_string(),
            c_source: "int is_negative_char(char value) { if (value < 0) { return 1; } return 0; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "type_uncertainty"),
            "{:?}",
            result.errors
        );
        assert!(result
            .type_map
            .uncertainties
            .iter()
            .any(|uncertainty| uncertainty.c_type == "char"));
        assert!(!result
            .rust_code
            .contains("pub fn is_negative_char(value: u8)"));
    }

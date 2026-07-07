#[cfg(test)]
mod tests {
    //! Behavior-regression locks for the legacy string translator, moved here
    //! from tests/bounded_translation.rs when the `translate_slice` export was
    //! demoted from the public API (P1-R6). The legacy translator is retired to
    //! a compatibility candidate source: these tests pin its existing emitted
    //! Rust text and legacy-specific refusal paths so they cannot drift, and
    //! they must not be used as a basis for extending its C coverage. New
    //! forward translation coverage belongs to the clang-lowered typed IR route
    //! and its artifact-level integration tests.

    use super::translate_slice;
    use crate::{BuildProfile, SliceSpec};

    // Minimal copy of the shared `profile` helper from
    // tests/bounded_translation.rs so the moved tests keep their original
    // build-profile inputs verbatim.
    fn profile(clang_available: bool) -> BuildProfile {
        BuildProfile {
            include_paths: vec!["/tmp/lib/include".to_string()],
            defines: vec!["_GNU_SOURCE".to_string()],
            target: None,
            clang_ast_fixture: None,
            target_triple: Some("x86_64-unknown-linux-gnu".to_string()),
            abi: Some("linux-gnu".to_string()),
            compiler_command_source: "compile_commands.json".to_string(),
            clang_available,
        }
    }

    #[test]
    fn translates_structured_integer_function_and_emits_type_map_and_cfg() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "add-one".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_one".to_string(),
            c_source: "int add_one(int value) { return value + 1; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn add_one(value: i32) -> i32"));
        assert!(result.rust_code.contains("value + 1"));
        assert_eq!(result.type_map.mappings[0].c_type, "int");
        assert_eq!(result.type_map.mappings[0].rust_type, "i32");
        assert_eq!(result.cfg.functions[0].name, "add_one");
        assert_eq!(result.cfg.functions[0].blocks[0].terminator, "return");
        assert!(result.pointer_graph.nodes.is_empty());
        assert_eq!(result.plan.unsupported_node_count, 0);
    }

    #[test]
    fn pointer_out_param_generates_safe_public_boundary_and_pointer_graph() {
        let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn uv_ip4_addr(ip: &str, port: i32)"));
        assert!(!result.rust_code.contains("*mut sockaddr_in"));
        assert_eq!(result.pointer_graph.nodes.len(), 2);
        assert!(result
            .pointer_graph
            .nodes
            .iter()
            .any(|node| node.id == "ip" && node.role == "borrowed_input"));
        assert!(result
            .pointer_graph
            .nodes
            .iter()
            .any(|node| node.id == "addr" && node.role == "out_param"));
        let addr = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "addr")
            .expect("addr pointer node");
        assert!(addr.write_effects.contains(&"addr->sin_family".to_string()));
        assert!(addr
            .read_effects
            .contains(&"addr->sin_family = AF_INET".to_string()));
        assert_eq!(result.plan.unsafe_candidate_count, 0);
    }

    #[test]
    fn bounded_pointer_index_write_generates_safe_boundary_and_decision() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "fill-first".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "fill_first".to_string(),
            c_source: "int fill_first(int* out, int value) { out[0] = value; return 0; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("pub fn fill_first(value: i32)"));
        assert!(!result.rust_code.contains("*mut"));
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert_eq!(out.role, "out_param");
        assert!(out.write_effects.contains(&"out[0]".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-index-write".to_string()));
    }

    #[test]
    fn bounded_pointer_index_compound_assignment_records_decision() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "add-first".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_first".to_string(),
            c_source: "int add_first(int* out, int value) { out[0] += value; return 0; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert!(out.write_effects.contains(&"out[0]".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-index-write".to_string()));
    }

    #[test]
    fn bounded_input_buffer_read_generates_safe_slice_boundary_and_decisions() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-i32-buffer".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_i32_buffer".to_string(),
        c_source: "int sum_i32_buffer(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + values[i]; } out[0] = total; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn sum_i32_buffer(values: &[i32], len: i32)"));
        assert!(result
            .rust_code
            .contains("total = total + values[i as usize];"));
        assert!(!result.rust_code.contains("*const"));
        assert!(!result.rust_code.contains("*mut"));
        let values = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "values")
            .expect("values pointer node");
        assert_eq!(values.role, "borrowed_input");
        assert!(values.read_effects.contains(&"values[i]".to_string()));
        assert!(values
            .boundary_decisions
            .contains(&"bounded_input_buffer".to_string()));
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert_eq!(out.role, "out_param");
        assert!(out.write_effects.contains(&"out[0]".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-input-buffer-read".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-index-write".to_string()));
    }

    #[test]
    fn bounded_pointer_arithmetic_read_generates_safe_slice_boundary_and_decisions() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-i32-ptr-arith".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_i32_ptr_arith".to_string(),
        c_source: "int sum_i32_ptr_arith(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + *(values + i); } out[0] = total; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn sum_i32_ptr_arith(values: &[i32], len: i32)"));
        assert!(result
            .rust_code
            .contains("total = total + values[i as usize];"));
        assert!(!result.rust_code.contains("*(values + i)"));
        assert!(!result.rust_code.contains("*const"));
        assert!(!result.rust_code.contains("*mut"));
        let values = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "values")
            .expect("values pointer node");
        assert_eq!(values.role, "borrowed_input");
        assert!(values.read_effects.contains(&"values[i]".to_string()));
        assert!(values.read_effects.contains(&"*(values + i)".to_string()));
        assert!(values
            .boundary_decisions
            .contains(&"bounded_input_buffer".to_string()));
        assert!(values
            .boundary_decisions
            .contains(&"bounded_pointer_arithmetic_input_read".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-input-buffer-read".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
    }

    #[test]
    fn flashdb_crc32_byte_cursor_loop_blocks_without_legacy_canned_template() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "real-fdb-calc-crc32".to_string(),
            source_commit: "93d1755".to_string(),
            function_name: "fdb_calc_crc32".to_string(),
            c_source: "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size)
{
    const uint8_t *p;

    p = (const uint8_t *)buf;
    crc = crc ^ ~0U;

    while (size--) {
        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
    }

    return crc ^ ~0U;
}"
            .to_string(),
            fixture_hash: "real-fdb-calc-crc32-fixture".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.rust_code.is_empty());
        assert!(!result.rust_code.contains("crc32_update_byte"));
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"crc32-byte-cursor-loop".to_string()));
        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_syntax"),
            "{:?}",
            result.errors
        );
        assert!(result
            .errors
            .iter()
            .any(|error| error.message.contains("increment/decrement")));
    }

    #[test]
    fn bounded_pointer_arithmetic_output_write_generates_safe_mut_slice_boundary_and_decisions() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "fill-i32-ptr-arith-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "fill_i32_ptr_arith_out".to_string(),
        c_source: "int fill_i32_ptr_arith_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn fill_i32_ptr_arith_out(out: &mut [i32], len: i32, value: i32)"));
        assert!(result.rust_code.contains("out[i as usize] = value;"));
        assert!(!result.rust_code.contains("*(out + i)"));
        assert!(!result.rust_code.contains("*mut"));
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert_eq!(out.role, "out_param");
        assert_eq!(out.rust_boundary, "&mut [i32]");
        assert!(out.write_effects.contains(&"out[i]".to_string()));
        assert!(out.write_effects.contains(&"*(out + i)".to_string()));
        assert!(out
            .boundary_decisions
            .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .lvalue_kinds
            .contains(&"bounded_pointer_arithmetic_output_buffer".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-output-write".to_string()));
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
    }

    #[test]
    fn bounded_pointer_arithmetic_writes_do_not_count_as_input_buffer_reads() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "ptr-arith-write".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "ptr_arith_write".to_string(),
        c_source: "int ptr_arith_write(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(!result
            .cfg
            .functions
            .iter()
            .flat_map(|function| function.blocks.iter())
            .flat_map(|block| block.statement_kinds.iter())
            .any(|kind| kind == "bounded_input_buffer_read"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
    }

    #[test]
    fn translates_primitive_declaration_assignment_and_return() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "local-state".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "local_state".to_string(),
        c_source:
            "int local_state(int value) { int total = value + 1; total = total + 2; return total; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("let mut total: i32 = value + 1;"));
        assert!(result.rust_code.contains("total = total + 2;"));
        assert!(result.rust_code.contains("return total;"));
        assert!(result.type_map.mappings.iter().any(|mapping| {
            mapping.symbol == "total" && mapping.c_type == "int" && mapping.rust_type == "i32"
        }));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"primitive_declaration".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"assignment".to_string()));
    }

    #[test]
    fn translates_if_else_with_cfg_branch_edges() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "clamp".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "clamp_non_negative".to_string(),
        c_source: "int clamp_non_negative(int value) { if (value < 0) { return 0; } else { return value; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("if value < 0 {"));
        assert!(result.rust_code.contains("} else {"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"if".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .edges
            .iter()
            .any(|edge| edge.starts_with("entry->if-")));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"structured-if".to_string()));
    }

    #[test]
    fn translates_while_loop_with_cfg_back_edge() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-while".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_while".to_string(),
        c_source: "int sum_while(int limit) { int total = 0; while (limit > 0) { total = total + limit; limit = limit - 1; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("while limit > 0 {"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"while".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .edges
            .iter()
            .any(|edge| edge.starts_with("entry->while-")));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"structured-while".to_string()));
    }

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
}

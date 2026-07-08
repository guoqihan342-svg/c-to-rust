    // Behavior-regression locks for the legacy string translator, moved here
    // from tests/bounded_translation.rs when the `translate_slice` export was
    // demoted from the public API (P1-R6). The legacy translator is retired to
    // a compatibility candidate source: these tests pin its existing emitted
    // Rust text and legacy-specific refusal paths so they cannot drift, and
    // they must not be used as a basis for extending its C coverage. New
    // forward translation coverage belongs to the clang-lowered typed IR route
    // and its artifact-level integration tests.

    use super::translate_slice;
    use crate::{BuildProfile, CBoundary, CDirectDependency, SliceSpec};

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
    fn record_pointer_nested_scalar_identity_return_generates_candidate() {
        let spec = SliceSpec {
        target_id: "flashdb".to_string(),
        slice_id: "real-fdb-kv-to-blob".to_string(),
        source_commit: "f9d0421315c564fb890a1b14eee77b290e0d7bbe".to_string(),
        function_name: "fdb_kv_to_blob".to_string(),
        c_source: "fdb_blob_t fdb_kv_to_blob(fdb_kv_t kv, fdb_blob_t blob) { blob->saved.meta_addr = kv->addr.start; blob->saved.addr = kv->addr.value; blob->saved.len = kv->value_len; return blob; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
        c_boundary: CBoundary {
            direct_dependencies: vec![
                CDirectDependency {
                    kind: "type".to_string(),
                    name: "fdb_kv_t".to_string(),
                    source: "inc/fdb_def.h#typedef struct fdb_kv *fdb_kv_t".to_string(),
                    source_span: None,
                    value: None,
                },
                CDirectDependency {
                    kind: "type".to_string(),
                    name: "fdb_blob_t".to_string(),
                    source: "inc/fdb_def.h#typedef struct fdb_blob *fdb_blob_t".to_string(),
                    source_span: None,
                    value: None,
                },
            ],
            ..CBoundary::default()
        },
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("pub struct FdbKvAddr"), "{}", result.rust_code);
        assert!(result.rust_code.contains("pub struct FdbBlobSaved"), "{}", result.rust_code);
        assert!(
            result
                .rust_code
                .contains("pub fn fdb_kv_to_blob<'a>(kv: &FdbKv, blob: &'a mut FdbBlob) -> &'a mut FdbBlob"),
            "{}",
            result.rust_code
        );
        assert!(result.rust_code.contains("blob.saved.meta_addr = kv.addr.start;"));
        assert!(result.rust_code.contains("blob.saved.addr = kv.addr.value;"));
        assert!(result.rust_code.contains("blob.saved.len = kv.value_len;"));
        assert!(result.rust_code.contains("return blob;"));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"mutable-record-pointer-nested-scalar-field-write".to_string()));
        assert_eq!(result.plan.unsupported_node_count, 0);
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

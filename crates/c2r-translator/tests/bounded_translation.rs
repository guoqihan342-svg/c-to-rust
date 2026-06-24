use std::{
    fs,
    time::{SystemTime, UNIX_EPOCH},
};

use c2r_translator::{translate_slice, write_translation_artifacts, BuildProfile, SliceSpec};

fn profile(clang_available: bool) -> BuildProfile {
    BuildProfile {
        include_paths: vec!["/tmp/lib/include".to_string()],
        defines: vec!["_GNU_SOURCE".to_string()],
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
fn blocks_pointer_out_param_without_observable_write() {
    let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr-no-write".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source:
            "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { return 0; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_pointer_pattern"));
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
fn blocks_unsupported_local_declaration_type_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "unknown-local".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "unknown_local".to_string(),
        c_source: "int unknown_local(int value) { alias_t local = value; return value; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_syntax"));
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
fn translates_simple_call_expression_and_records_call_rule() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "call".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "call_hook".to_string(),
        c_source: "int call_hook(int value) { observe(value); return value; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
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
fn blocks_unknown_or_unsupported_statement_without_rust_draft() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "unsupported-stmt".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "unsupported_stmt".to_string(),
        c_source: "int unsupported_stmt(int value) { value += 1; return value; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_syntax"));
}

#[test]
fn unsupported_goto_blocks_translation_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "goto-case".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "again".to_string(),
        c_source: "int again(int x) { again: x++; if (x < 10) goto again; return x; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_control_flow"));
    assert!(result.cfg.functions[0]
        .unsupported_control_flow
        .iter()
        .any(|node| node == "goto"));
}

#[test]
fn unsupported_switch_blocks_translation_until_cfg_relooper_exists() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "switch-case".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "choose".to_string(),
        c_source: "int choose(int x) { switch (x) { case 1: return 1; default: return 0; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_control_flow"));
    assert!(result.cfg.functions[0]
        .unsupported_control_flow
        .iter()
        .any(|node| node == "switch"));
}

#[test]
fn missing_clang_profile_records_type_uncertainty() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "ambiguous".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "uses_alias".to_string(),
        c_source: "alias_t uses_alias(alias_t value) { return value; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .type_map
        .uncertainties
        .iter()
        .any(|item| item.reason.contains("clang-backed type extraction")));
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "type_uncertainty"));
}

#[test]
fn writes_translation_artifacts_for_l3_manifest_binding() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "add-one".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "add_one".to_string(),
        c_source: "int add_one(int value) { return value + 1; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
    };
    let out_dir = std::env::temp_dir().join(format!(
        "c2r-translator-test-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.target_id, "demo");
    assert_eq!(manifest.slice_id, "add-one");
    for path in [
        "l3-add-one-auto-translation-plan.json",
        "l3-add-one-auto-translation-events.jsonl",
        "l3-add-one-type-map.json",
        "l3-add-one-cfg.json",
        "l3-add-one-pointer-graph.json",
        "l3-add-one-ai-candidate-manifest.json",
        "l3-add-one-blocked-repairs.json",
        "l3-add-one-rust-draft.rs",
    ] {
        assert!(out_dir.join(path).exists(), "{path}");
    }
    let plan = fs::read_to_string(out_dir.join("l3-add-one-auto-translation-plan.json")).unwrap();
    assert!(plan.contains("\"status\": \"generated\""));
}

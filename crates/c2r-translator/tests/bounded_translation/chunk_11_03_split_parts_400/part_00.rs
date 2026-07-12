#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_multi_var_decl_stmt_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-multi-var-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("multi_decl.c");
    fs::write(
        &source_file,
        "int multi_decl(void) { int a = 1, b = 2; return a + b; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "multi_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name: a_name,
        init: Some(IrExpr::LitInt { value: a_value, .. }),
        ..
    }, IrStmt::Decl {
        name: b_name,
        init: Some(IrExpr::LitInt { value: b_value, .. }),
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Binary { .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected two declarations followed by return, got {:?}",
            function.body
        );
    };
    assert_eq!(a_name, "a");
    assert_eq!(*a_value, 1);
    assert_eq!(b_name, "b");
    assert_eq!(*b_value, 2);

    let emitted = emit_rust_from_ir(function)
        .unwrap_or_else(|error| panic!("emit multi var decl: {error:?}"));
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn multi_decl() -> i32"), "{rust}");
    assert!(rust.contains("let mut a: i32 = 1i32;"), "{rust}");
    assert!(rust.contains("let mut b: i32 = 2i32;"), "{rust}");
    assert!(
        rust.contains("return a.checked_add(b).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-multi-var-decl", rust);
}

#[test]
fn pointer_field_writes_record_lvalue_and_boundary_decisions() {
    let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr-fields".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; addr->sin_port = port; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ip4-addr-fields");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.slice_id, "ip4-addr-fields");
    let plan = json_file(out_dir.join("l3-ip4-addr-fields-auto-translation-plan.json"));
    assert_eq!(
        plan["translation_source"]["selected"],
        "legacy-string-translator"
    );
    let plan_errors = plan["errors"].as_array().expect("plan errors");
    assert!(
        plan_errors.iter().all(|error| {
            let kind = error["kind"].as_str().unwrap_or_default();
            kind.starts_with("legacy_") && kind.ends_with("_retired")
        }),
        "expected only retired-legacy diagnostics, got {plan_errors:?}"
    );

    let pointer_graph = json_file(out_dir.join("l3-ip4-addr-fields-pointer-graph.json"));
    assert_eq!(pointer_graph["status"], "recorded");
    let addr = pointer_graph["pointer_graph"]["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|node| node["id"] == "addr")
        .expect("addr pointer node");
    let write_effects = addr["write_effects"]
        .as_array()
        .expect("addr write effects");
    assert!(write_effects
        .iter()
        .any(|effect| effect == "addr->sin_family"));
    assert!(write_effects
        .iter()
        .any(|effect| effect == "addr->sin_port"));

    let cfg = json_file(out_dir.join("l3-ip4-addr-fields-cfg.json"));
    let lvalue_kinds = cfg["cfg"]["functions"][0]["blocks"][0]["lvalue_kinds"]
        .as_array()
        .expect("lvalue kinds");
    let addr_decisions = addr["boundary_decisions"]
        .as_array()
        .expect("addr boundary decisions");

    assert!(lvalue_kinds.iter().any(|kind| kind == "pointer_field"));
    assert!(addr_decisions
        .iter()
        .any(|decision| decision == "safe_wrapper_candidate"));
    assert!(plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .iter()
        .any(|rule| rule == "pointer-field-write"));
}

#[test]
fn unproven_input_buffer_read_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-buffer-read".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_buffer_read".to_string(),
        c_source: "int bad_buffer_read(const int* values, int i, int* out) { out[0] = values[i]; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-buffer-read");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-bad-buffer-read-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-buffer-read-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-bad-buffer-read-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unproven_pointer_arithmetic_read_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-read".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_read".to_string(),
        c_source: "int bad_ptr_arith_read(const int* values, int i, int* out) { out[0] = *(values + i); return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-ptr-arith-read");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-read-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-ptr-arith-read-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-read-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unproven_pointer_arithmetic_output_write_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_out".to_string(),
        c_source:
            "int bad_ptr_arith_out(int* out, int i, int value) { *(out + i) = value; return 0; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-ptr-arith-out");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-out-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-ptr-arith-out-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-out-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn complex_pointer_arithmetic_output_write_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-complex-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_complex_out".to_string(),
        c_source: "int bad_ptr_arith_complex_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i + 1) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-ptr-arith-complex-out");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-complex-out-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-ptr-arith-complex-out-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_lvalue"),
        "{:?}",
        plan["errors"]
    );
    let events = fs::read_to_string(
        out_dir.join("l3-bad-ptr-arith-complex-out-auto-translation-events.jsonl"),
    )
    .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

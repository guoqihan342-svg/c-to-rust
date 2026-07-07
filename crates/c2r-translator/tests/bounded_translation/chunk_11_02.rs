#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_strlen_model_with_target_abi_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let source_root = unique_out_dir("clang-real-strlen-target-abi-lower");
    let source_dir = source_root.join("src");
    fs::create_dir_all(&source_dir).unwrap();
    let source_file = source_dir.join("name_len.c");
    fs::write(
        &source_file,
        "typedef unsigned long size_t;\nsize_t strlen(const char *);\nsize_t name_len(const char *name) { return strlen(name); }\n",
    )
    .unwrap();
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "strlen-target-abi",
        "source_commit": "source-sha",
        "function_name": "name_len",
        "c_source": "size_t name_len(const char *name) { return strlen(name); }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root.to_string_lossy().replace('\\', "/"),
        "source_file": "src/name_len.c",
        "source_file_hashes": {
            "src/name_len.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/name_len.c",
            "line_start": 3,
            "line_end": 3,
            "byte_start": 63,
            "byte_end": 119,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "char_width": 8,
                "plain_char_signed": true,
                "short_width": 16,
                "long_width": 64,
                "long_long_width": 64,
                "pointer_width": 64
            },
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "x86_64-unknown-linux-gnu",
            "compiler_command_source": "unit-test",
            "clang_available": true
        }
    }))
    .unwrap();
    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_parse_spec_report(&environment, &parse_spec);

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Call {
            callee, args, ty, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected strlen return call, got {:?}", function.body);
    };
    assert_eq!(callee, "strlen");
    assert_eq!(args.len(), 1);
    assert_eq!(ty.spelled, "size_t");

    let emitted = emit_rust_from_ir(function).expect("emit strlen model from real clang AST");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn name_len(name: &[i8]) -> usize"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return name.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\");"
        ),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-strlen-model", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_nested_direct_call_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-direct-call-lower");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("nested_direct_call.c");
    fs::write(
        &source_file,
        "int inner(int value) { return value + 1; }\nint outer(int value) { return value; }\nint nested_direct_call(int value) { return outer(inner(value)); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "nested_direct_call");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Call { callee, args, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected nested direct call return, got {:?}",
            function.body
        );
    };
    assert_eq!(callee, "outer");
    let [IrExpr::Call {
        callee: inner_callee,
        args: inner_args,
        ..
    }] = args.as_slice()
    else {
        panic!("expected one nested direct call arg, got {args:?}");
    };
    assert_eq!(inner_callee, "inner");
    assert_eq!(inner_args.len(), 1);

    let emitted = emit_rust_from_ir(function).expect("emit nested direct call from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn nested_direct_call(value: i32) -> i32"));
    assert!(rust.contains("return outer(inner(value));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-direct-call",
        &format!(
            "fn inner(value: i32) -> i32 {{ value + 1 }}\nfn outer(value: i32) -> i32 {{ value }}\n{rust}"
        ),
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_multiple_nested_direct_call_args_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-multiple-nested-direct-call-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("multiple_nested_direct_call.c");
    fs::write(
        &source_file,
        "int left(int value) { return value + 1; }\nint right(int value) { return value + 2; }\nint outer2(int a, int b) { return a + b; }\nint multiple_nested_direct_call(int value) { return outer2(left(value), right(value)); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "multiple_nested_direct_call",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    let message = report
        .errors
        .first()
        .map(|error| error.message.as_str())
        .unwrap_or("");
    assert!(
        message.contains("multiple nested call arguments are outside the bounded call subset"),
        "{message}"
    );
}

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

#[test]
fn unsupported_complex_lvalues_block_without_false_success() {
    for (slice_id, function_name, c_source) in [
        (
            "unbounded-index",
            "unbounded_index",
            "int unbounded_index(int* out, int i, int value) { out[i] = value; return 0; }",
        ),
        (
            "field-assignment",
            "field_assignment",
            "int field_assignment(int value) { state.field = value; return value; }",
        ),
        (
            "pointer-arithmetic-complex",
            "pointer_arithmetic_complex",
            "int pointer_arithmetic_complex(int* out, int i, int value) { *(out + i + 1) = value; return 0; }",
        ),
    ] {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: slice_id.to_string(),
            source_commit: "1234567".to_string(),
            function_name: function_name.to_string(),
            c_source: c_source.to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir(slice_id);

        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

        assert_eq!(manifest.status, "blocked", "{slice_id}");
        let rust_draft =
            fs::read_to_string(out_dir.join(format!("l3-{slice_id}-rust-draft.rs"))).unwrap();
        assert!(rust_draft.is_empty(), "{slice_id}: {rust_draft}");
        let plan = json_file(out_dir.join(format!("l3-{slice_id}-auto-translation-plan.json")));
        assert_eq!(plan["status"], "blocked", "{slice_id}");
        assert!(
            plan["errors"]
                .as_array()
                .expect("plan errors")
                .iter()
                .any(|error| error["kind"] == "unsupported_lvalue"),
            "{slice_id}: {:?}",
            plan["errors"]
        );
        let events = fs::read_to_string(
            out_dir.join(format!("l3-{slice_id}-auto-translation-events.jsonl")),
        )
        .unwrap();
        assert!(
            !events.contains("\"event\":\"translation_generated\""),
            "{slice_id}"
        );
    }
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
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ip4-addr-no-write");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-ip4-addr-no-write-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-ip4-addr-no-write-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_pointer_pattern"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-ip4-addr-no-write-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
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
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("unknown-local");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-unknown-local-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-unknown-local-auto-translation-plan.json"));
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
        fs::read_to_string(out_dir.join("l3-unknown-local-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

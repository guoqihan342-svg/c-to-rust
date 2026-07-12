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
#[test]
fn blocks_unsupported_call_expressions_without_rust_draft() {
    for (slice_id, c_source) in [
        (
            "nested-call-expression",
            "int nested_call_expression(int value) { return helper(other(value)); }",
        ),
        (
            "function-pointer-call-expression",
            "int function_pointer_call_expression(int value) { return (*fp)(value); }",
        ),
        (
            "side-effect-call-argument",
            "int side_effect_call_argument(int value) { return helper(value++); }",
        ),
        (
            "assert-call-expression",
            "int assert_call_expression(int value) { assert(value); return value; }",
        ),
    ] {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: slice_id.to_string(),
            source_commit: "1234567".to_string(),
            function_name: slice_id.replace('-', "_"),
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
                .any(|error| error["kind"] == "unsupported_syntax"),
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

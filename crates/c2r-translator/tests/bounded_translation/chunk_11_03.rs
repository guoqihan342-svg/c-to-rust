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

#[test]
fn blocks_increment_expression_value_without_rust_draft() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "inc-expression".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "inc_expression".to_string(),
        c_source: "int inc_expression(int value) { return value++; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("inc-expression");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-inc-expression-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-inc-expression-auto-translation-plan.json"));
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
        fs::read_to_string(out_dir.join("l3-inc-expression-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn blocks_unknown_or_unsupported_statement_without_rust_draft() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "unsupported-stmt".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "unsupported_stmt".to_string(),
        c_source: "int unsupported_stmt(int value) { value ? value : 0; return value; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("unsupported-stmt");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-unsupported-stmt-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-unsupported-stmt-auto-translation-plan.json"));
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
        fs::read_to_string(out_dir.join("l3-unsupported-stmt-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
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
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("goto-case");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-goto-case-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-goto-case-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_control_flow"),
        "{:?}",
        plan["errors"]
    );
    let cfg = json_file(out_dir.join("l3-goto-case-cfg.json"));
    let unsupported = cfg["cfg"]["functions"][0]["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(
        unsupported.iter().any(|node| node == "goto"),
        "{unsupported:?}"
    );
    let events =
        fs::read_to_string(out_dir.join("l3-goto-case-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unsupported_goto_records_minimal_cfg_blocks_and_edges() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "goto-cfg-evidence".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "again".to_string(),
        c_source: "int again(int x) { again: x++; if (x < 10) goto again; return x; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let out_dir = unique_out_dir("goto-cfg-evidence");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-goto-cfg-evidence-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let cfg = json_file(out_dir.join("l3-goto-cfg-evidence-cfg.json"));
    let function = &cfg["cfg"]["functions"][0];
    let unsupported = function["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(unsupported.iter().any(|node| node == "label:again"));
    assert!(unsupported.iter().any(|node| node == "goto:again"));
    assert!(unsupported
        .iter()
        .any(|node| node == "relooper_refusal:goto"));
    let structured = &function["structured_control_flow"];
    assert!(
        structured.is_object(),
        "goto refusal should carry structured recovery evidence: {structured:?}"
    );
    assert_eq!(structured["has_goto"], true);
    assert_eq!(structured["has_switch"], false);
    assert_eq!(structured["relooper_required"], true);
    assert!(structured["relooper_preconditions"]
        .as_array()
        .expect("relooper preconditions")
        .iter()
        .any(|item| item == "goto_target_resolved"));
    assert!(structured["relooper_refusals"]
        .as_array()
        .expect("relooper refusals")
        .iter()
        .any(|item| item == "goto_requires_structured_recovery"));
    assert!(structured["scope_note"]
        .as_str()
        .expect("scope note")
        .contains("no Rust candidate lowering"));
    let blocks = function["blocks"].as_array().expect("cfg blocks");
    assert!(blocks.iter().any(|block| block["id"] == "label-again"));
    assert!(blocks.iter().any(|block| block["id"] == "goto-again"));
    let edges: Vec<&Value> = blocks
        .iter()
        .flat_map(|block| block["edges"].as_array().expect("block edges").iter())
        .collect();
    assert!(edges.iter().any(|edge| **edge == "entry->goto-again"));
    assert!(edges.iter().any(|edge| **edge == "goto-again->label-again"));
    assert!(!edges.iter().any(|edge| **edge == "entry->goto"));
    let events =
        fs::read_to_string(out_dir.join("l3-goto-cfg-evidence-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
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
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("switch-case");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-switch-case-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-switch-case-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_control_flow"),
        "{:?}",
        plan["errors"]
    );
    let cfg = json_file(out_dir.join("l3-switch-case-cfg.json"));
    let unsupported = cfg["cfg"]["functions"][0]["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(
        unsupported.iter().any(|node| node == "switch"),
        "{unsupported:?}"
    );
    let events =
        fs::read_to_string(out_dir.join("l3-switch-case-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unsupported_switch_records_case_default_cfg_edges() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "switch-cfg-evidence".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "choose".to_string(),
        c_source: "int choose(int x) { switch (x) { case 1: return 1; default: return 0; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let out_dir = unique_out_dir("switch-cfg-evidence");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-switch-cfg-evidence-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let cfg = json_file(out_dir.join("l3-switch-cfg-evidence-cfg.json"));
    let function = &cfg["cfg"]["functions"][0];
    let unsupported = function["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(unsupported.iter().any(|node| node == "case:1"));
    assert!(unsupported.iter().any(|node| node == "default"));
    assert!(unsupported
        .iter()
        .any(|node| node == "relooper_refusal:switch"));
    let structured = &function["structured_control_flow"];
    assert!(
        structured.is_object(),
        "switch refusal should carry structured recovery evidence: {structured:?}"
    );
    assert_eq!(structured["has_goto"], false);
    assert_eq!(structured["has_switch"], true);
    assert_eq!(structured["relooper_required"], true);
    assert!(structured["relooper_preconditions"]
        .as_array()
        .expect("relooper preconditions")
        .iter()
        .any(|item| item == "switch_cases_enumerated"));
    assert!(structured["relooper_refusals"]
        .as_array()
        .expect("relooper refusals")
        .iter()
        .any(|item| item == "switch_requires_structured_recovery"));
    assert!(structured["scope_note"]
        .as_str()
        .expect("scope note")
        .contains("no Rust candidate lowering"));
    let blocks = function["blocks"].as_array().expect("cfg blocks");
    assert!(blocks.iter().any(|block| block["id"] == "switch-0"));
    assert!(blocks.iter().any(|block| block["id"] == "case-1"));
    assert!(blocks.iter().any(|block| block["id"] == "default"));
    let edges: Vec<&Value> = blocks
        .iter()
        .flat_map(|block| block["edges"].as_array().expect("block edges").iter())
        .collect();
    assert!(edges.iter().any(|edge| **edge == "entry->switch-0"));
    assert!(edges.iter().any(|edge| **edge == "switch-0->case-1"));
    assert!(edges.iter().any(|edge| **edge == "switch-0->default"));
    assert!(!edges.iter().any(|edge| **edge == "entry->switch"));
    let events =
        fs::read_to_string(out_dir.join("l3-switch-cfg-evidence-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
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
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ambiguous");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-ambiguous-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let type_map = json_file(out_dir.join("l3-ambiguous-type-map.json"));
    assert_eq!(type_map["status"], "uncertain");
    assert!(
        type_map["type_map"]["uncertainties"]
            .as_array()
            .expect("type map uncertainties")
            .iter()
            .any(|item| item["reason"]
                .as_str()
                .expect("uncertainty reason")
                .contains("clang-backed type extraction")),
        "{:?}",
        type_map["type_map"]["uncertainties"]
    );
    let plan = json_file(out_dir.join("l3-ambiguous-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "type_uncertainty"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-ambiguous-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
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
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("add-one");

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
    assert!(plan.contains("\"status\": \"blocked\""));
    assert!(plan.contains("\"kind\": \"legacy_"));
    assert!(plan.contains("_retired\""));
    let events =
        fs::read_to_string(out_dir.join("l3-add-one-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[cfg(not(feature = "clang-frontend"))]
#[test]
fn default_translation_artifacts_do_not_emit_clang_dry_run() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("no-clang-dry-run");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-dry-run.json")
        .exists());
    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-lowering-report.json")
        .exists());
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-lowering-report.json")));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_frontend_feature_writes_dry_run_artifact_from_real_tu_metadata() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc", "tests"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("clang-dry-run");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let dry_run = json_file(out_dir.join("l3-real-fdb-calc-crc32-clang-dry-run.json"));

    assert!(manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
    assert_eq!(dry_run["schema_version"], 1);
    assert_eq!(dry_run["artifact_kind"], "clang-dry-run");
    assert_eq!(dry_run["status"], "diagnostic_only");
    assert_eq!(dry_run["frontend"], "clang");
    assert_eq!(dry_run["claim_boundary"]["role"], "diagnostic_only");
    assert_eq!(dry_run["active_frontend"]["kind"], "clang_ast_dump_json");
    assert_eq!(dry_run["active_frontend"]["uses_libclang"], false);
    assert_eq!(dry_run["dry_run"]["status"], "diagnostic_only");
    assert_eq!(dry_run["dry_run"]["source_file"], "src/fdb_utils.c");
    assert_eq!(
        dry_run["dry_run"]["arguments"],
        serde_json::json!([
            "-IC:/src/FlashDB/inc",
            "-IC:/src/FlashDB/tests",
            "-DFDB_USING_FILE_POSIX_MODE"
        ])
    );
    assert_eq!(
        dry_run["metadata"]["source_file_hashes"]["src/fdb_utils.c"],
        "source-file-sha"
    );
    assert!(dry_run["errors"].as_array().unwrap().is_empty());
}

#[cfg(all(feature = "clang-frontend", not(feature = "clang-lowering-report")))]
#[test]
fn clang_frontend_feature_does_not_emit_lowering_report_without_opt_in() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/demo",
        "source_file": "add_one.c",
        "source_file_hashes": {
            "add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "add_one.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 43,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("no-clang-lowering-report");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(!out_dir
        .join("l3-add-one-clang-lowering-report.json")
        .exists());
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-add-one-clang-lowering-report.json")));
}

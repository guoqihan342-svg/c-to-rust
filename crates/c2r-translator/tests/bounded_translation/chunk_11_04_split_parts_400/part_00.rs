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

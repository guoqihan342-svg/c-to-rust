#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_stats_sequence_fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/renamed_interior_alias_stats_sequence_ast.json"
    ))
    .expect("renamed stats sequence fixture JSON")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_stats_sequence_abi() -> TargetAbiProfile {
    TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        int_width: 32,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_stats_sequence_function_mut(ast: &mut Value) -> &mut Value {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["kind"] == "FunctionDecl")
        .expect("fixture function")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_stats_sequence_body_mut(ast: &mut Value) -> &mut Vec<Value> {
    renamed_stats_sequence_function_mut(ast)["inner"]
        .as_array_mut()
        .expect("fixture function children")
        .iter_mut()
        .find(|node| node["kind"] == "CompoundStmt")
        .and_then(|body| body["inner"].as_array_mut())
        .expect("fixture function body")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_stats_sequence_failure(ast: &Value, abi: Option<&TargetAbiProfile>) -> String {
    match lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        ast,
        "record_survey",
        abi,
    ) {
        Ok(lowered) => {
            emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
                .expect_err("out-of-bound renamed stats sequence must fail closed")
                .reason
        }
        Err(error) => error.message,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn renamed_interior_alias_stats_sequence_emits_candidate_and_runs() {
    let ast = renamed_stats_sequence_fixture();
    let abi = renamed_stats_sequence_abi();
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "record_survey",
        Some(&abi),
    )
    .expect("lower renamed stats sequence fixture");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed stats sequence fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("let reading = &mut ledger.current_reading;"),
        "{rust}"
    );
    assert!(
        rust.contains("ledger.revision_count = ledger.revision_count.wrapping_add(1u32);"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "ledger.accepted_total = ledger.accepted_total.wrapping_add((reading.accepted_units as usize));"
        ),
        "{rust}"
    );
    assert!(
        rust.contains(
            "ledger.rejected_total = ledger.rejected_total.wrapping_add((reading.rejected_units as usize));"
        ),
        "{rust}"
    );
    assert!(rust.contains("return true;"), "{rust}");
    assert!(!rust.contains("unsafe"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-renamed-interior-alias-stats-sequence",
        rust,
        "let mut zero = SurveyLedger { current_reading: ReadingPair { accepted_units: 0u32, rejected_units: 0u32 }, revision_count: 0u32, accepted_total: 0usize, rejected_total: 0usize };\n\
assert!(record_survey(&mut zero));\n\
assert_eq!(zero.revision_count, 1u32);\n\
assert_eq!(zero.accepted_total, 0usize);\n\
assert_eq!(zero.rejected_total, 0usize);\n\
let mut ordinary = SurveyLedger { current_reading: ReadingPair { accepted_units: 3u32, rejected_units: 5u32 }, revision_count: 8u32, accepted_total: 11usize, rejected_total: 13usize };\n\
assert!(record_survey(&mut ordinary));\n\
assert_eq!(ordinary.revision_count, 9u32);\n\
assert_eq!(ordinary.accepted_total, 14usize);\n\
assert_eq!(ordinary.rejected_total, 18usize);\n\
let mut wrapped = SurveyLedger { current_reading: ReadingPair { accepted_units: 3u32, rejected_units: 1u32 }, revision_count: u32::MAX, accepted_total: usize::MAX - 1usize, rejected_total: usize::MAX };\n\
assert!(record_survey(&mut wrapped));\n\
assert_eq!(wrapped.revision_count, 0u32);\n\
assert_eq!(wrapped.accepted_total, 1usize);\n\
assert_eq!(wrapped.rejected_total, 0usize);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn renamed_stats_sequence_rejects_missing_abi_duplicate_target_and_duplicate_source() {
    let abi = renamed_stats_sequence_abi();
    let ast = renamed_stats_sequence_fixture();
    assert!(renamed_stats_sequence_failure(&ast, None).contains("target ABI"));

    let mut duplicate_target = renamed_stats_sequence_fixture();
    renamed_stats_sequence_body_mut(&mut duplicate_target)[3]["inner"][0]["name"] =
        Value::String("accepted_total".to_string());
    let reason = renamed_stats_sequence_failure(&duplicate_target, Some(&abi));
    assert!(reason.contains("must not overlap"), "{reason}");

    let mut duplicate_source = renamed_stats_sequence_fixture();
    renamed_stats_sequence_body_mut(&mut duplicate_source)[3]["inner"][1]["inner"][0]["inner"][0]
        ["name"] = Value::String("accepted_units".to_string());
    let reason = renamed_stats_sequence_failure(&duplicate_source, Some(&abi));
    assert!(reason.contains("sources must be distinct"), "{reason}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn renamed_stats_sequence_rejects_order_extra_statement_and_increment_drift() {
    let abi = renamed_stats_sequence_abi();

    let mut out_of_order = renamed_stats_sequence_fixture();
    renamed_stats_sequence_body_mut(&mut out_of_order).swap(1, 2);
    let reason = renamed_stats_sequence_failure(&out_of_order, Some(&abi));
    assert!(
        reason.contains("assignment-call")
            || reason.contains("stats sequence")
            || reason.contains("bounded"),
        "{reason}"
    );

    let mut extra_statement = renamed_stats_sequence_fixture();
    let extra = renamed_stats_sequence_body_mut(&mut extra_statement)[1].clone();
    renamed_stats_sequence_body_mut(&mut extra_statement).insert(4, extra);
    let reason = renamed_stats_sequence_failure(&extra_statement, Some(&abi));
    assert!(reason.contains("bounded"), "{reason}");

    let mut decrement = renamed_stats_sequence_fixture();
    renamed_stats_sequence_body_mut(&mut decrement)[1]["opcode"] = Value::String("--".to_string());
    let reason = renamed_stats_sequence_failure(&decrement, Some(&abi));
    assert!(
        reason.contains("normalized addition") || reason.contains("increment"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn renamed_stats_sequence_rejects_terminal_drift_and_projection_overlap() {
    let abi = renamed_stats_sequence_abi();

    let mut terminal_false = renamed_stats_sequence_fixture();
    renamed_stats_sequence_body_mut(&mut terminal_false)[4]["inner"][0]["inner"][0]["value"] =
        Value::String("0".to_string());
    let reason = renamed_stats_sequence_failure(&terminal_false, Some(&abi));
    assert!(reason.contains("fixed bool true"), "{reason}");

    let mut non_bool_terminal = renamed_stats_sequence_fixture();
    renamed_stats_sequence_body_mut(&mut non_bool_terminal)[4]["inner"][0] = serde_json::json!({
        "kind": "IntegerLiteral",
        "value": "1",
        "type": { "qualType": "int" }
    });
    let reason = renamed_stats_sequence_failure(&non_bool_terminal, Some(&abi));
    assert!(reason.contains("fixed bool true"), "{reason}");

    let mut overlap = renamed_stats_sequence_fixture();
    renamed_stats_sequence_body_mut(&mut overlap)[2]["inner"][0]["name"] =
        Value::String("current_reading".to_string());
    let reason = renamed_stats_sequence_failure(&overlap, Some(&abi));
    assert!(
        reason.contains("overlaps the aliased owner projection")
            || reason.contains("does not match declared type"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn renamed_stats_sequence_rejects_second_pointer_root_and_owner_alias_noalias() {
    let abi = renamed_stats_sequence_abi();

    let mut second_root = renamed_stats_sequence_fixture();
    let function = renamed_stats_sequence_function_mut(&mut second_root);
    function["type"]["qualType"] =
        Value::String("_Bool (struct SurveyLedger *, struct SurveyLedger *)".to_string());
    function["inner"]
        .as_array_mut()
        .expect("fixture function children")
        .insert(
            1,
            serde_json::json!({
                "kind": "ParmVarDecl",
                "name": "shadow_ledger",
                "type": { "qualType": "struct SurveyLedger *" }
            }),
        );
    let reason = renamed_stats_sequence_failure(&second_root, Some(&abi));
    assert!(
        reason.contains("one pointer param") || reason.contains("one mutable owner pointer root"),
        "{reason}"
    );

    let ast = renamed_stats_sequence_fixture();
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "record_survey",
        Some(&abi),
    )
    .expect("lower renamed stats sequence fixture");
    let error = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        EmitPolicy {
            noalias_param_pairs: vec![NoAliasParamPair {
                readonly_param: "reading".to_string(),
                mutable_param: "ledger".to_string(),
            }],
            ..EmitPolicy::default()
        },
    )
    .expect_err("owner/interior alias noalias assumption must fail closed");
    assert!(
        error.reason.contains("must not be modeled as noalias"),
        "{}",
        error.reason
    );
}

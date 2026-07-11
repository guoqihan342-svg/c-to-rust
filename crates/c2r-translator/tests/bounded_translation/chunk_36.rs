#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn guarded_stats_fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/guarded_interior_stats_ast.json"
    ))
    .expect("guarded stats fixture JSON")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn guarded_stats_abi() -> TargetAbiProfile {
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
fn guarded_stats_body_mut(ast: &mut Value) -> &mut Vec<Value> {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["kind"] == "FunctionDecl")
        .and_then(|function| function["inner"].as_array_mut())
        .and_then(|children| {
            children
                .iter_mut()
                .find(|node| node["kind"] == "CompoundStmt")
        })
        .and_then(|body| body["inner"].as_array_mut())
        .expect("fixture function body")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn guarded_stats_condition_mut(ast: &mut Value) -> &mut Value {
    &mut guarded_stats_body_mut(ast)[1]["inner"][0]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn guarded_stats_then_body_mut(ast: &mut Value) -> &mut Vec<Value> {
    guarded_stats_body_mut(ast)[1]["inner"][1]["inner"]
        .as_array_mut()
        .expect("guarded stats then body")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn guarded_stats_failure(ast: &Value) -> String {
    let abi = guarded_stats_abi();
    match lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        ast,
        "update_totals",
        Some(&abi),
    ) {
        Ok(lowered) => {
            emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
                .expect_err("out-of-bound guarded stats sequence must fail closed")
                .reason
        }
        Err(error) => error.message,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn guarded_interior_stats_sequence_emits_candidate_and_runs() {
    let ast = guarded_stats_fixture();
    let abi = guarded_stats_abi();
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "update_totals",
        Some(&abi),
    )
    .expect("lower guarded stats fixture");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit guarded stats fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let sample = &mut totals.active;"), "{rust}");
    let first_equality = rust.find("sample.mode == 7i32").expect("first equality");
    let conjunction = rust[first_equality..].find("&&").expect("logical and") + first_equality;
    let second_equality = rust
        .find("sample.ready as i32) == 1i32")
        .expect("second equality");
    let increment = rust
        .find("totals.visits = totals.visits.wrapping_add(1u32);")
        .expect("owner increment");
    let first_add = rust
        .find(
            "totals.first_total = totals.first_total.wrapping_add((sample.first_units as usize));",
        )
        .expect("first size add");
    let second_add = rust
        .find("totals.second_total = totals.second_total.wrapping_add((sample.second_units as usize));")
        .expect("second size add");
    assert!(
        first_equality < conjunction
            && conjunction < second_equality
            && second_equality < increment
            && increment < first_add
            && first_add < second_add,
        "{rust}"
    );
    assert!(rust.contains("return true;"), "{rust}");
    assert!(rust.contains("return false;"), "{rust}");
    assert!(!rust.contains("unsafe"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-guarded-interior-stats",
        rust,
        "let mut hit = Totals { active: Sample { mode: 7i32, ready: true, first_units: 3u32, second_units: 5u32 }, visits: 8u32, first_total: 11usize, second_total: 13usize };\n\
assert!(update_totals(&mut hit));\n\
assert_eq!((hit.visits, hit.first_total, hit.second_total), (9u32, 14usize, 18usize));\n\
let mut first_miss = Totals { active: Sample { mode: 6i32, ready: true, first_units: 3u32, second_units: 5u32 }, visits: 8u32, first_total: 11usize, second_total: 13usize };\n\
assert!(!update_totals(&mut first_miss));\n\
assert_eq!((first_miss.visits, first_miss.first_total, first_miss.second_total), (8u32, 11usize, 13usize));\n\
let mut second_miss = Totals { active: Sample { mode: 7i32, ready: false, first_units: 3u32, second_units: 5u32 }, visits: 8u32, first_total: 11usize, second_total: 13usize };\n\
assert!(!update_totals(&mut second_miss));\n\
assert_eq!((second_miss.visits, second_miss.first_total, second_miss.second_total), (8u32, 11usize, 13usize));\n\
let mut wrapped = Totals { active: Sample { mode: 7i32, ready: true, first_units: 3u32, second_units: 1u32 }, visits: u32::MAX, first_total: usize::MAX - 1usize, second_total: usize::MAX };\n\
assert!(update_totals(&mut wrapped));\n\
assert_eq!((wrapped.visits, wrapped.first_total, wrapped.second_total), (0u32, 1usize, 0usize));",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn guarded_stats_sequence_rejects_logical_and_comparison_order_drift() {
    let mut logical_or = guarded_stats_fixture();
    guarded_stats_condition_mut(&mut logical_or)["opcode"] = Value::String("||".to_string());
    let reason = guarded_stats_failure(&logical_or);
    assert!(
        reason.contains("ordered equalities joined by &&"),
        "{reason}"
    );

    let mut reversed = guarded_stats_fixture();
    guarded_stats_condition_mut(&mut reversed)["inner"]
        .as_array_mut()
        .expect("guard comparisons")
        .swap(0, 1);
    let reason = guarded_stats_failure(&reversed);
    assert!(reason.contains("first equality"), "{reason}");

    let mut not_equal = guarded_stats_fixture();
    guarded_stats_condition_mut(&mut not_equal)["inner"][0]["opcode"] =
        Value::String("!=".to_string());
    let reason = guarded_stats_failure(&not_equal);
    assert!(
        reason.contains("first comparison must be exact equality"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn guarded_stats_sequence_rejects_operand_and_true_literal_drift() {
    let mut swapped_operands = guarded_stats_fixture();
    guarded_stats_condition_mut(&mut swapped_operands)["inner"][0]["inner"]
        .as_array_mut()
        .expect("first equality operands")
        .swap(0, 1);
    let reason = guarded_stats_failure(&swapped_operands);
    assert!(reason.contains("directly read alias C int"), "{reason}");

    let mut false_literal = guarded_stats_fixture();
    guarded_stats_condition_mut(&mut false_literal)["inner"][1]["inner"][1]["value"] =
        Value::String("0".to_string());
    let reason = guarded_stats_failure(&false_literal);
    assert!(reason.contains("promoted bool with true"), "{reason}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn guarded_stats_sequence_rejects_else_and_body_shape_drift() {
    let mut with_else = guarded_stats_fixture();
    guarded_stats_body_mut(&mut with_else)[1]["inner"]
        .as_array_mut()
        .expect("if children")
        .push(serde_json::json!({
            "kind": "CompoundStmt",
            "inner": [{
                "kind": "ReturnStmt",
                "inner": [{
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralToBoolean",
                    "type": { "qualType": "_Bool" },
                    "inner": [{
                        "kind": "IntegerLiteral",
                        "value": "0",
                        "type": { "qualType": "int" }
                    }]
                }]
            }]
        }));
    let reason = guarded_stats_failure(&with_else);
    assert!(reason.contains("must not have an else branch"), "{reason}");

    let mut extra_effect = guarded_stats_fixture();
    let extra = guarded_stats_then_body_mut(&mut extra_effect)[0].clone();
    guarded_stats_then_body_mut(&mut extra_effect).push(extra);
    let reason = guarded_stats_failure(&extra_effect);
    assert!(reason.contains("exactly increment/add/add"), "{reason}");

    let mut reordered = guarded_stats_fixture();
    guarded_stats_then_body_mut(&mut reordered).swap(0, 1);
    let reason = guarded_stats_failure(&reordered);
    assert!(
        reason.contains("increment") || reason.contains("direct owner u32"),
        "{reason}"
    );

    let mut false_success = guarded_stats_fixture();
    guarded_stats_then_body_mut(&mut false_success)[3]["inner"][0]["inner"][0]["value"] =
        Value::String("0".to_string());
    let reason = guarded_stats_failure(&false_success);
    assert!(reason.contains("fixed bool true"), "{reason}");

    let mut true_miss = guarded_stats_fixture();
    guarded_stats_body_mut(&mut true_miss)[2]["inner"][0]["inner"][0]["value"] =
        Value::String("1".to_string());
    let reason = guarded_stats_failure(&true_miss);
    assert!(reason.contains("fixed bool false"), "{reason}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn zero_start_assignment_call_requires_exact_u32_offset_parameter() {
    for case in ["missing_offset", "wrong_offset_type"] {
        let function_name = format!("reject_{case}");
        let mut ast = zero_start_assignment_call_fixture(&function_name);
        let function = interior_reborrow_function_mut(&mut ast, &function_name);
        match case {
            "missing_offset" => {
                function["inner"]
                    .as_array_mut()
                    .unwrap()
                    .retain(|node| node["name"] != "offset");
            }
            "wrong_offset_type" => {
                let offset = function["inner"]
                    .as_array_mut()
                    .unwrap()
                    .iter_mut()
                    .find(|node| node["name"] == "offset")
                    .unwrap();
                offset["type"]["qualType"] = serde_json::json!("int");
            }
            _ => unreachable!(),
        }
        let reason = zero_start_assignment_call_failure(&ast, &function_name);
        assert_zero_start_failure(&reason, case);
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn zero_start_assignment_call_rejects_condition_and_path_drift() {
    for case in [
        "nonzero_condition",
        "incorrect_condition",
        "condition_path",
        "assignment_path",
    ] {
        let function_name = format!("reject_{case}");
        let mut ast = zero_start_assignment_call_fixture(&function_name);
        let outer_if = zero_start_outer_if_mut(&mut ast, &function_name);
        match case {
            "nonzero_condition" => {
                outer_if["inner"][0]["inner"][1]["value"] = serde_json::json!("1");
            }
            "incorrect_condition" => {
                outer_if["inner"][0]["opcode"] = serde_json::json!("!=");
            }
            "condition_path" => {
                outer_if["inner"][0]["inner"][0]["inner"][0]["name"] =
                    serde_json::json!("guard");
            }
            "assignment_path" => {
                outer_if["inner"][1]["inner"][0]["inner"][0]["name"] =
                    serde_json::json!("guard");
            }
            _ => unreachable!(),
        }
        let reason = zero_start_assignment_call_failure(&ast, &function_name);
        assert_zero_start_failure(&reason, case);
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn zero_start_assignment_call_rejects_branch_order_and_extra_statement() {
    for case in ["branch_drift", "branch_order", "extra_statement"] {
        let function_name = format!("reject_{case}");
        let mut ast = zero_start_assignment_call_fixture(&function_name);
        let outer_if = zero_start_outer_if_mut(&mut ast, &function_name);
        match case {
            "branch_drift" => {
                outer_if["inner"].as_array_mut().unwrap().pop();
            }
            "branch_order" => {
                let branches = outer_if["inner"].as_array_mut().unwrap();
                branches.swap(1, 2);
            }
            "extra_statement" => {
                outer_if["inner"][1]["inner"]
                    .as_array_mut()
                    .unwrap()
                    .push(serde_json::json!({
                        "kind": "ReturnStmt",
                        "inner": [run_once_reborrow_bool(0)]
                    }));
            }
            _ => unreachable!(),
        }
        let reason = zero_start_assignment_call_failure(&ast, &function_name);
        assert_zero_start_failure(&reason, case);
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn zero_start_assignment_call_rejects_local_provenance_drift() {
    for case in ["alias_not_first", "seed_not_parameter_copy"] {
        let function_name = format!("reject_{case}");
        let mut ast = zero_start_assignment_call_fixture(&function_name);
        let function = interior_reborrow_function_mut(&mut ast, &function_name);
        let body = interior_reborrow_body_mut(function);
        match case {
            "alias_not_first" => body.swap(0, 1),
            "seed_not_parameter_copy" => {
                body[1]["inner"][0]["inner"][0]["inner"][0]["referencedDecl"]["name"] =
                    serde_json::json!("unbound_seed");
            }
            _ => unreachable!(),
        }
        let reason = zero_start_assignment_call_failure(&ast, &function_name);
        assert_zero_start_failure(&reason, case);
    }
}

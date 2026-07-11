#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn owner_sibling_size_add_fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/interior_alias_owner_sibling_size_add_ast.json"
    ))
    .expect("owner sibling size add fixture JSON")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn owner_sibling_size_add_abi() -> TargetAbiProfile {
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
fn owner_sibling_size_add_body_mut(ast: &mut Value) -> &mut Vec<Value> {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["kind"] == "FunctionDecl")
        .and_then(|function| function["inner"].as_array_mut())
        .and_then(|children| children.iter_mut().find(|node| node["kind"] == "CompoundStmt"))
        .and_then(|body| body["inner"].as_array_mut())
        .expect("fixture function body")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn owner_sibling_size_add_failure(ast: &Value, abi: Option<&TargetAbiProfile>) -> String {
    match lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        ast,
        "accumulate_quantity",
        abi,
    ) {
        Ok(lowered) => emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect_err("out-of-bound owner sibling size add must fail closed")
            .reason,
        Err(error) => error.message,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_owner_sibling_size_add_from_interior_alias_without_clang() {
    let ast = owner_sibling_size_add_fixture();
    let abi = owner_sibling_size_add_abi();
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "accumulate_quantity",
        Some(&abi),
    )
    .expect("lower owner sibling size add fixture");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit owner sibling size add fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let element = &mut container.selected;"), "{rust}");
    assert!(
        rust.contains("container.total = container.total.wrapping_add((element.quantity as usize));"),
        "{rust}"
    );
    assert!(rust.contains("return true;"), "{rust}");
    assert!(!rust.contains("unsafe"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-owner-sibling-size-add-from-interior-alias",
        rust,
        "let mut ordinary = Container { selected: Element { quantity: 3u32, stamp: 0u32 }, total: 9usize, other_total: 4usize };\n\
assert!(accumulate_quantity(&mut ordinary));\n\
assert_eq!(ordinary.total, 12usize);\n\
let mut zero = Container { selected: Element { quantity: 0u32, stamp: 1u32 }, total: 7usize, other_total: 5usize };\n\
assert!(accumulate_quantity(&mut zero));\n\
assert_eq!(zero.total, 7usize);\n\
let mut wrapped = Container { selected: Element { quantity: 3u32, stamp: 2u32 }, total: usize::MAX - 1usize, other_total: 6usize };\n\
assert!(accumulate_quantity(&mut wrapped));\n\
assert_eq!(wrapped.total, 1usize);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn owner_sibling_size_add_rejects_missing_abi_overlap_and_second_pointer_hop() {
    let abi = owner_sibling_size_add_abi();
    let ast = owner_sibling_size_add_fixture();
    assert!(owner_sibling_size_add_failure(&ast, None).contains("target ABI"));

    let mut overlap = owner_sibling_size_add_fixture();
    owner_sibling_size_add_body_mut(&mut overlap)[1]["inner"][0]["name"] =
        Value::String("selected".to_string());
    let reason = owner_sibling_size_add_failure(&overlap, Some(&abi));
    assert!(reason.contains("overlap") || reason.contains("type"), "{reason}");

    let mut second_hop = owner_sibling_size_add_fixture();
    let rhs_member = owner_sibling_size_add_body_mut(&mut second_hop)[1]["inner"][1]["inner"][0]
        ["inner"][0]
        .clone();
    owner_sibling_size_add_body_mut(&mut second_hop)[1]["inner"][1]["inner"][0]["inner"][0] =
        serde_json::json!({
            "kind": "MemberExpr",
            "name": "stamp",
            "isArrow": false,
            "type": { "qualType": "unsigned int" },
            "inner": [rhs_member]
        });
    let reason = owner_sibling_size_add_failure(&second_hop, Some(&abi));
    assert!(reason.contains("projection") || reason.contains("direct"), "{reason}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn owner_sibling_size_add_rejects_alias_reuse_effects_and_type_drift() {
    let abi = owner_sibling_size_add_abi();

    let mut repeated = owner_sibling_size_add_fixture();
    let rhs = owner_sibling_size_add_body_mut(&mut repeated)[1]["inner"][1].clone();
    owner_sibling_size_add_body_mut(&mut repeated)[1]["inner"][1] = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "+",
        "type": { "desugaredQualType": "unsigned long", "qualType": "size_t" },
        "inner": [rhs.clone(), rhs]
    });
    let reason = owner_sibling_size_add_failure(&repeated, Some(&abi));
    assert!(reason.contains("simple integer") || reason.contains("direct alias"), "{reason}");

    let mut call = owner_sibling_size_add_fixture();
    owner_sibling_size_add_body_mut(&mut call)[1]["inner"][1] = serde_json::json!({
        "kind": "CallExpr",
        "type": { "qualType": "unsigned int" },
        "inner": []
    });
    let reason = owner_sibling_size_add_failure(&call, Some(&abi));
    assert!(reason.contains("simple integer") || reason.contains("CallExpr"), "{reason}");

    let mut signed = owner_sibling_size_add_fixture();
    let compound = &mut owner_sibling_size_add_body_mut(&mut signed)[1];
    compound["computeLHSType"] = serde_json::json!({ "qualType": "long" });
    compound["computeResultType"] = serde_json::json!({ "qualType": "long" });
    let reason = owner_sibling_size_add_failure(&signed, Some(&abi));
    assert!(reason.contains("type") || reason.contains("unsigned ABI size_t"), "{reason}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn owner_sibling_size_add_rejects_owner_alias_noalias_assumption() {
    let ast = owner_sibling_size_add_fixture();
    let abi = owner_sibling_size_add_abi();
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "accumulate_quantity",
        Some(&abi),
    )
    .expect("lower owner sibling size add fixture");
    let error = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        EmitPolicy {
            noalias_param_pairs: vec![NoAliasParamPair {
                readonly_param: "element".to_string(),
                mutable_param: "container".to_string(),
            }],
            ..EmitPolicy::default()
        },
    )
    .expect_err("owner/interior alias noalias assumption must fail closed");
    assert!(error.reason.contains("must not be modeled as noalias"), "{}", error.reason);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn owner_sibling_size_add_requires_fixed_terminal_true_for_bool_carrier() {
    let abi = owner_sibling_size_add_abi();

    let mut terminal_false = owner_sibling_size_add_fixture();
    owner_sibling_size_add_body_mut(&mut terminal_false)[2]["inner"][0]["inner"][0]["value"] =
        Value::String("0".to_string());
    let reason = owner_sibling_size_add_failure(&terminal_false, Some(&abi));
    assert!(reason.contains("fixed bool true"), "{reason}");

    let mut non_fixed = owner_sibling_size_add_fixture();
    owner_sibling_size_add_body_mut(&mut non_fixed)[2]["inner"][0] = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "IntegralToBoolean",
        "type": { "qualType": "_Bool" },
        "inner": [{
            "kind": "UnaryOperator",
            "opcode": "!",
            "type": { "qualType": "int" },
            "inner": [{
                "kind": "IntegerLiteral",
                "value": "0",
                "type": { "qualType": "int" }
            }]
        }]
    });
    let reason = owner_sibling_size_add_failure(&non_fixed, Some(&abi));
    assert!(reason.contains("fixed bool true"), "{reason}");

    let mut extra = owner_sibling_size_add_fixture();
    let extra_add = owner_sibling_size_add_body_mut(&mut extra)[1].clone();
    owner_sibling_size_add_body_mut(&mut extra).insert(2, extra_add);
    let reason = owner_sibling_size_add_failure(&extra, Some(&abi));
    assert!(
        reason.contains("run-once")
            || reason.contains("bounded")
            || reason.contains("sentinel"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn owner_sibling_size_add_accepts_two_statement_void_carrier() {
    let mut ast = owner_sibling_size_add_fixture();
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["kind"] == "FunctionDecl")
        .map(|function| {
            function["type"]["qualType"] =
                Value::String("void (struct Container *)".to_string())
        })
        .expect("fixture function");
    owner_sibling_size_add_body_mut(&mut ast).pop();

    let abi = owner_sibling_size_add_abi();
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "accumulate_quantity",
        Some(&abi),
    )
    .expect("lower two-statement void owner sibling size add");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit two-statement void owner sibling size add");
    assert!(emitted.rust.contains("pub fn accumulate_quantity"));
    assert!(!emitted.rust.contains("-> bool"));
    assert!(!emitted.rust.contains("return true;"));
}

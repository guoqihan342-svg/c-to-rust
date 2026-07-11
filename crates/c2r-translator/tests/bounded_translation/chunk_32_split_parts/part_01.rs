#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_do_while_empty_body_tail_still_emits() {
    let function_name = "advance_alias_with_empty_body";
    let ast = interior_reborrow_do_while_tail_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower existing empty-body interior reborrow do-while tail");
    emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        assignment_call_reborrow_policy(),
    )
    .expect("emit existing empty-body interior reborrow do-while tail");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_do_while_body_call_emits_and_runs_in_order() {
    let function_name = "advance_renamed_alias_until_sentinel";
    let body_callee = "touch_alias_before_advance";
    let ast = interior_reborrow_do_while_body_call_fixture(function_name, body_callee);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower interior reborrow do-while body call and assignment-call tail");
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        assignment_call_reborrow_policy(),
    )
    .expect("emit interior reborrow do-while body call and assignment-call tail");
    let rust = &emitted.rust;
    assert!(rust.contains("let cursor = &mut owner.current;"), "{rust}");
    assert_eq!(
        rust.matches("touch_alias_before_advance(").count(),
        1,
        "{rust}"
    );
    assert_eq!(rust.matches("sample_next(").count(), 1, "{rust}");
    assert!(
        rust.find("touch_alias_before_advance(") < rust.find("sample_next("),
        "{rust}"
    );
    assert!(
        rust.contains("if !((cursor.nested.leaf != 4294967295u32))"),
        "{rust}"
    );

    let runtime = format!(
        "use std::sync::atomic::{{AtomicU32, Ordering}};\n\
         static BODY_CALLS: AtomicU32 = AtomicU32::new(0);\n\
         static TAIL_CALLS: AtomicU32 = AtomicU32::new(0);\n\
         fn touch_alias_before_advance(source: &mut Source, alias: &mut Node) -> u32 {{\
             let body_call = BODY_CALLS.fetch_add(1, Ordering::SeqCst);\
             assert_eq!(TAIL_CALLS.load(Ordering::SeqCst), body_call);\
             source.delta = source.delta.wrapping_add(10);\
             alias.nested.guard = alias.nested.guard.wrapping_add(1);\
             41\
         }}\n\
         fn sample_next(source: &mut Source, seed: &mut Seed, alias: &mut Node) -> u32 {{\
             let tail_call = TAIL_CALLS.fetch_add(1, Ordering::SeqCst);\
             assert_eq!(BODY_CALLS.load(Ordering::SeqCst), tail_call + 1);\
             source.delta = source.delta.wrapping_add(1);\
             seed.token = seed.token.wrapping_add(1);\
             assert_eq!(alias.tag, 13);\
             assert_eq!(alias.nested.guard, 12 + tail_call);\
             if tail_call == 0 {{ 17 }} else {{ u32::MAX }}\
         }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-interior-reborrow-do-while-body-call",
        &runtime,
        r#"
    BODY_CALLS.store(0, Ordering::SeqCst);
    TAIL_CALLS.store(0, Ordering::SeqCst);
    let mut source = Source { delta: 3 };
    let mut owner = Owner {
        current: Node { nested: Cell { leaf: 9, guard: 11 }, tag: 13 },
        marker: 19,
    };
    assert!(!advance_renamed_alias_until_sentinel(
        &mut owner,
        &mut source,
        Seed { token: 5 },
    ));
    assert_eq!(BODY_CALLS.load(Ordering::SeqCst), 2);
    assert_eq!(TAIL_CALLS.load(Ordering::SeqCst), 2);
    assert_eq!(source.delta, 25);
    assert_eq!(owner.current.nested.leaf, u32::MAX);
    assert_eq!(owner.current.nested.guard, 13);
    assert_eq!(owner.marker, 19);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn interior_reborrow_do_while_body_call_rejects_second_statement_and_noncall() {
    let function_name = "reject_second_body_statement";
    let mut ast = interior_reborrow_do_while_body_call_fixture(function_name, "observe_once");
    let second_call = interior_reborrow_do_while_body_call_mut(&mut ast, function_name).clone();
    let tail = interior_reborrow_do_while_tail_mut(&mut ast, function_name);
    tail["inner"][0]["inner"] = serde_json::json!([second_call.clone(), second_call]);
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(reason.contains("at most one direct-call"), "{reason}");

    let function_name = "reject_noncall_body_expression";
    let mut ast = interior_reborrow_do_while_body_call_fixture(function_name, "observe_once");
    *interior_reborrow_do_while_body_call_mut(&mut ast, function_name) = serde_json::json!({
        "kind": "IntegerLiteral",
        "value": "7",
        "type": { "qualType": "unsigned int" }
    });
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(
        reason.contains("one direct call expression")
            || reason.contains("outside the current clang lowering skeleton"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn interior_reborrow_do_while_body_call_rejects_nested_call_and_extra_root() {
    let function_name = "reject_nested_body_call";
    let mut ast = interior_reborrow_do_while_body_call_fixture(function_name, "observe_once");
    let call = interior_reborrow_do_while_body_call_mut(&mut ast, function_name);
    let source_arg = call["inner"][1].clone();
    call["inner"][1] = serde_json::json!({
        "kind": "CallExpr",
        "type": { "qualType": "struct Source *" },
        "inner": [
            {
                "kind": "ImplicitCastExpr",
                "castKind": "FunctionToPointerDecay",
                "type": { "qualType": "struct Source *(*)(struct Source *)" },
                "inner": [{
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "struct Source *(struct Source *)" },
                    "referencedDecl": { "kind": "FunctionDecl", "name": "nested_source" }
                }]
            },
            source_arg
        ]
    });
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(
        reason.contains("call root arg must be a direct root")
            || reason.contains("record pointer constructor call first argument"),
        "{reason}"
    );

    let function_name = "reject_extra_mutable_root";
    let mut ast = interior_reborrow_do_while_body_call_fixture(function_name, "observe_once");
    let call = interior_reborrow_do_while_body_call_mut(&mut ast, function_name);
    let duplicate_alias = call["inner"][2].clone();
    call["inner"]
        .as_array_mut()
        .expect("body call operands")
        .push(duplicate_alias);
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(
        reason.contains("exact call-root/same-alias arguments"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn interior_reborrow_do_while_body_call_rejects_repeated_root_and_owner_sibling_read() {
    let function_name = "reject_repeated_mutable_root";
    let mut ast = interior_reborrow_do_while_body_call_fixture(function_name, "observe_once");
    let call = interior_reborrow_do_while_body_call_mut(&mut ast, function_name);
    let repeated_root = call["inner"][1].clone();
    call["inner"][2] = repeated_root;
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(reason.contains("same-alias arg drifted"), "{reason}");

    let function_name = "reject_same_owner_sibling_read";
    let mut ast = interior_reborrow_do_while_body_call_fixture(function_name, "observe_once");
    let call = interior_reborrow_do_while_body_call_mut(&mut ast, function_name);
    call["inner"][2] = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "MemberExpr",
            "name": "marker",
            "isArrow": true,
            "type": { "qualType": "unsigned int" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "struct Owner *" },
                "referencedDecl": { "kind": "ParmVarDecl", "name": "owner" }
            }]
        }]
    });
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(
        reason.contains("same-alias arg must be a direct root")
            || reason.contains("does not match parameter type"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn interior_reborrow_do_while_body_call_rejects_comparison_drift() {
    let function_name = "reject_tail_comparison_drift";
    let mut ast = interior_reborrow_do_while_body_call_fixture(function_name, "observe_once");
    let tail = interior_reborrow_do_while_tail_mut(&mut ast, function_name);
    tail["inner"][1]["opcode"] = serde_json::json!("==");
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(reason.contains("exact inequality"), "{reason}");
}

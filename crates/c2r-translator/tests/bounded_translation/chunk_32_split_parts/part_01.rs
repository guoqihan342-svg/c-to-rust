#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_do_while_tail_assignment_call_emits_and_runs() {
    let function_name = "advance_alias_until_sentinel";
    let ast = interior_reborrow_do_while_tail_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower interior reborrow do-while assignment-call tail");
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        assignment_call_reborrow_policy(),
    )
    .expect("emit interior reborrow do-while assignment-call tail");
    let rust = &emitted.rust;
    assert!(rust.contains("let cursor = &mut owner.current;"), "{rust}");
    assert_eq!(rust.matches("sample_next(").count(), 1, "{rust}");
    assert!(
        rust.contains("if !((cursor.nested.leaf != 4294967295u32))"),
        "{rust}"
    );

    let runtime = format!(
        "use std::sync::atomic::{{AtomicU32, Ordering}};\n\
         static CALLS: AtomicU32 = AtomicU32::new(0);\n\
         fn sample_next(source: &mut Source, seed: &mut Seed, alias: &mut Node) -> u32 {{\
             let call = CALLS.fetch_add(1, Ordering::SeqCst);\
             source.delta = source.delta.wrapping_add(1);\
             seed.token = seed.token.wrapping_add(1);\
             assert_eq!(alias.tag, 13);\
             if call == 0 {{ 17 }} else {{ u32::MAX }}\
         }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-interior-reborrow-do-while-tail",
        &runtime,
        r#"
    CALLS.store(0, Ordering::SeqCst);
    let mut source = Source { delta: 3 };
    let mut owner = Owner {
        current: Node { nested: Cell { leaf: 9, guard: 11 }, tag: 13 },
        marker: 19,
    };
    assert!(!advance_alias_until_sentinel(
        &mut owner,
        &mut source,
        Seed { token: 5 },
    ));
    assert_eq!(CALLS.load(Ordering::SeqCst), 2);
    assert_eq!(source.delta, 5);
    assert_eq!(owner.current.nested.leaf, u32::MAX);
    assert_eq!(owner.current.nested.guard, 11);
    assert_eq!(owner.marker, 19);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn interior_reborrow_do_while_tail_rejects_nonempty_body_and_comparison_drift() {
    let function_name = "reject_nonempty_tail";
    let mut ast = interior_reborrow_do_while_tail_fixture(function_name);
    let extra_assignment = {
        let function = interior_reborrow_function_mut(&mut ast, function_name);
        let body = interior_reborrow_body_mut(function);
        body[3]["inner"][1]["inner"][0].clone()
    };
    let tail = interior_reborrow_do_while_tail_mut(&mut ast, function_name);
    tail["inner"][0]["inner"] = serde_json::json!([extra_assignment]);
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(
        reason.contains("empty C body") || reason.contains("normalized tail assignment"),
        "{reason}"
    );

    let function_name = "reject_tail_comparison_drift";
    let mut ast = interior_reborrow_do_while_tail_fixture(function_name);
    let tail = interior_reborrow_do_while_tail_mut(&mut ast, function_name);
    tail["inner"][1]["opcode"] = serde_json::json!("==");
    let reason = interior_reborrow_do_while_tail_failure(&ast, function_name);
    assert!(
        reason.contains("exact inequality"),
        "{reason}"
    );
}

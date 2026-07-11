#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_run_once_interior_reborrow_emits_safe_rust_and_runs() {
    let function_name = "apply_projected_step_once";
    let ast = run_once_reborrow_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower run-once interior reborrow without clang");
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        run_once_reborrow_policy(),
    )
    .expect("emit run-once interior reborrow");
    let rust = &emitted.rust;
    assert!(rust.contains("let cursor = &mut owner.current;"), "{rust}");
    assert!(rust.contains("cursor.nested.leaf = 0u32;"), "{rust}");
    assert!(
        rust.contains("owner.marker = owner.marker.wrapping_add(source.delta);"),
        "{rust}"
    );
    assert!(rust.contains("continue;"), "{rust}");
    assert!(!rust.contains("unsafe") && !rust.contains("*mut"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-run-once-interior-reborrow",
        rust,
        r#"
    let source = Source { delta: 3 };
    let mut owner = Owner {
        current: Node {
            nested: Cell { leaf: 9, guard: 11 },
            tag: 13,
        },
        marker: u32::MAX - 1,
    };
    assert!(apply_projected_step_once(&mut owner, &source));
    assert_eq!(owner.current.nested.leaf, 0);
    assert_eq!(owner.current.nested.guard, 11);
    assert_eq!(owner.current.tag, 13);
    assert_eq!(owner.marker, 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_run_once_interior_reborrow_requires_forward_noalias() {
    let function_name = "reject_run_once_noalias_drift";
    let ast = run_once_reborrow_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower noalias refusal fixture");
    let missing = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("missing noalias must fail closed");
    assert!(missing.reason.contains("noalias"), "{missing:?}");

    let reversed = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "owner".to_string(),
            mutable_param: "source".to_string(),
        }],
        ..Default::default()
    };
    let error = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        reversed,
    )
    .expect_err("reversed noalias must fail closed");
    assert!(error.reason.contains("noalias"), "{error:?}");
}

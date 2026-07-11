#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_zero_start_assignment_call_reborrow_emits_and_runs() {
    let function_name = "advance_from_zero_or_sample_once";
    let ast = zero_start_assignment_call_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower zero-start assignment-call carrier without clang");
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        assignment_call_reborrow_policy(),
    )
    .expect("emit zero-start assignment-call carrier");
    let rust = &emitted.rust;
    assert!(rust.contains("let cursor = &mut owner.current;"), "{rust}");
    assert!(
        rust.contains("if (cursor.nested.leaf == 0u32)"),
        "{rust}"
    );
    assert!(
        rust.contains("cursor.nested.leaf = seed_local.token.wrapping_add(offset);"),
        "{rust}"
    );
    assert_eq!(rust.matches("sample_next(").count(), 1, "{rust}");

    let runtime = format!(
        "use std::sync::atomic::{{AtomicU32, Ordering}};\n\
         static CALLS: AtomicU32 = AtomicU32::new(0);\n\
         fn sample_next(source: &mut Source, seed: &mut Seed, alias: &mut Node) -> u32 {{\
             CALLS.fetch_add(1, Ordering::SeqCst);\
             assert_ne!(source.delta, 0);\
             assert_ne!(alias.nested.leaf, 0);\
             match seed.token {{ 1 => u32::MAX, 2 => 0, _ => 17 }}\
         }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-zero-start-assignment-call-reborrow",
        &runtime,
        r#"
    let mut zero_source = Source { delta: 3 };
    let mut zero_owner = Owner {
        current: Node { nested: Cell { leaf: 0, guard: 11 }, tag: 13 },
        marker: 19,
    };
    assert!(!advance_from_zero_or_sample_once(
        &mut zero_owner,
        &mut zero_source,
        Seed { token: 40 },
        2,
    ));
    assert_eq!(CALLS.load(Ordering::SeqCst), 0);
    assert_eq!(zero_owner.current.nested.leaf, 42);
    assert_eq!(zero_owner.marker, 19);

    let mut hit_source = Source { delta: 3 };
    let mut hit_owner = Owner {
        current: Node { nested: Cell { leaf: 9, guard: 11 }, tag: 13 },
        marker: u32::MAX - 1,
    };
    assert!(advance_from_zero_or_sample_once(
        &mut hit_owner,
        &mut hit_source,
        Seed { token: 1 },
        5,
    ));
    assert_eq!(CALLS.load(Ordering::SeqCst), 1);
    assert_eq!(hit_owner.current.nested.leaf, 0);
    assert_eq!(hit_owner.marker, 1);

    let mut zero_miss_source = Source { delta: 5 };
    let mut zero_miss_owner = Owner {
        current: Node { nested: Cell { leaf: 23, guard: 29 }, tag: 31 },
        marker: 7,
    };
    assert!(!advance_from_zero_or_sample_once(
        &mut zero_miss_owner,
        &mut zero_miss_source,
        Seed { token: 2 },
        8,
    ));
    assert_eq!(CALLS.load(Ordering::SeqCst), 2);
    assert_eq!(zero_miss_owner.current.nested.leaf, 0);
    assert_eq!(zero_miss_owner.marker, 7);

    let mut miss_source = Source { delta: 7 };
    let mut miss_owner = Owner {
        current: Node { nested: Cell { leaf: 37, guard: 41 }, tag: 43 },
        marker: 47,
    };
    assert!(!advance_from_zero_or_sample_once(
        &mut miss_owner,
        &mut miss_source,
        Seed { token: 3 },
        9,
    ));
    assert_eq!(CALLS.load(Ordering::SeqCst), 3);
    assert_eq!(miss_owner.current.nested.leaf, 17);
    assert_eq!(miss_owner.marker, 47);

    let mut wrap_source = Source { delta: 11 };
    let mut wrap_owner = Owner {
        current: Node { nested: Cell { leaf: 0, guard: 53 }, tag: 59 },
        marker: 61,
    };
    assert!(!advance_from_zero_or_sample_once(
        &mut wrap_owner,
        &mut wrap_source,
        Seed { token: u32::MAX - 1 },
        5,
    ));
    assert_eq!(CALLS.load(Ordering::SeqCst), 3);
    assert_eq!(wrap_owner.current.nested.leaf, 3);
    assert_eq!(wrap_owner.marker, 61);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_interior_reborrow_emits_safe_projection_and_updates_owner() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-interior-reborrow");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("interior_reborrow.c");
    fs::write(
        &source_file,
        "typedef unsigned int u32;\n\
         typedef struct Node *NodeRef;\n\
         struct Cell { u32 leaf; u32 guard; };\n\
         struct Node { struct Cell nested; u32 tag; };\n\
         struct Owner { struct Node current; u32 marker; };\n\
         _Bool set_nested_leaf_via_projection(struct Owner *owner) {\n\
             NodeRef cursor = &(owner->current);\n\
             cursor->nested.leaf = 37U;\n\
             return 1;\n\
         }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);
    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "set_nested_leaf_via_projection",
    );
    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let emitted = emit_rust_from_ir_with_globals(
        report.function_ir.as_ref().expect("real clang function IR"),
        &report.globals,
    )
    .expect("emit real-clang interior reborrow");
    let rust = &emitted.rust;
    assert!(rust.contains("let cursor = &mut owner.current;"), "{rust}");
    assert!(rust.contains("cursor.nested.leaf = 37u32;"), "{rust}");
    assert!(rust.contains("return true;"), "{rust}");
    assert!(!rust.contains("unsafe") && !rust.contains("*mut"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-real-clang-interior-reborrow",
        rust,
        r#"
    let mut owner = Owner {
        current: Node {
            nested: Cell { leaf: 0, guard: 2 },
            tag: 3,
        },
        marker: 4,
    };
    assert!(set_nested_leaf_via_projection(&mut owner));
    assert_eq!(owner.current.nested.leaf, 37);
    assert_eq!(owner.current.nested.guard, 2);
"#,
    );
}

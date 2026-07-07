#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_mutable_pointer_add_deref_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mutable-pointer-add-deref-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_pointer_store.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\nvoid store_at_offset(int *out, size_t i, int value) { *(out + i) = value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "store_at_offset");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, .. }] = function.body.as_slice() else {
        panic!(
            "expected mutable pointer add-deref assignment, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Deref { .. }));

    let rust = emit_rust_from_ir(function)
        .expect("emit mutable pointer add-deref assignment from real clang AST");
    assert!(rust.contains("pub fn store_at_offset(mut out: &mut [i32], i: usize, value: i32)"));
    assert!(rust.contains("out[i as usize] = value;"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-mutable-pointer-add-deref-assignment",
        &rust,
    );
}

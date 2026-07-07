#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_while_continue_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-while-continue");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("skip_once.c");
    fs::write(
        &source_file,
        "int skip_once(int value) { while (value) { value = value - 1; if (value > 3) { continue; } value = value - 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "skip_once");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { body, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { .. }, IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Continue { .. }])
    ));

    let rust =
        emit_rust_from_ir(function).expect("emit typed IR while continue from real clang AST");
    assert!(rust.contains("pub fn skip_once(mut value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("continue;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-continue", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_loop_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-loop");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sum_to_limit.c");
    fs::write(
        &source_file,
        "int sum_to_limit(int limit) { int total = 0; for (int i = 0; i < limit; i++) { total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "sum_to_limit");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, .. }, IrStmt::For {
        init, step, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert_eq!(name, "total");
    assert!(matches!(init.as_slice(), [IrStmt::Decl { name, .. }] if name == "i"));
    assert!(matches!(step.as_deref(), Some(IrStmt::Assign { .. })));
    assert!(matches!(body.as_slice(), [IrStmt::Assign { .. }]));

    let rust = emit_rust_from_ir(function).expect("emit typed IR for loop from real clang AST");
    assert!(rust.contains("pub fn sum_to_limit(limit: i32) -> i32"));
    assert!(rust.contains("{\n        let mut i: i32 = 0i32;\n        while (i < limit) {"));
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\");"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-for-loop", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_continue_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-continue");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_for_continue.c");
    fs::write(
        &source_file,
        "int bad_for_continue(int limit) { int total = 0; for (int i = 0; i < limit; i++) { if (i) { continue; } total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_for_continue");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { .. }, IrStmt::For { body, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Continue { .. }])
    ));

    let rust = emit_rust_from_ir(function).expect("emit typed IR for continue from real clang AST");
    assert!(rust.contains("pub fn bad_for_continue(limit: i32) -> i32"));
    assert!(rust.contains("if i != 0i32 {"));
    assert!(
        rust.contains("                i = i.checked_add(1i32).expect(\"signed addition overflow\");\n                continue;"),
        "{rust:?}"
    );
    assert_eq!(
        rust.matches("i = i.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust:?}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-for-continue", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_while_break_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-while-break");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("stop_at_limit.c");
    fs::write(
        &source_file,
        "int stop_at_limit(int value) { while (value) { if (value > 3) { break; } value = value - 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "stop_at_limit");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { body, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Break { .. }])
    ));

    let rust = emit_rust_from_ir(function).expect("emit typed IR while break from real clang AST");
    assert!(rust.contains("pub fn stop_at_limit(mut value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("if (value > 3i32) {"));
    assert!(rust.contains("break;"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-break", &rust);
}
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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_while_without_braces_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-while-without-braces");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("countdown_no_braces.c");
    fs::write(
        &source_file,
        "int countdown_no_braces(int value) { while (value > 0) value = value + ~0; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "countdown_no_braces",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::Gt,
            ..
        }
    ));
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit no-brace while from real clang AST");
    assert!(rust.contains("pub fn countdown_no_braces(mut value: i32) -> i32"));
    assert!(rust.contains("while (value > 0i32) {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-without-braces", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_simple_if_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-simple-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_if.c");
    fs::write(
        &source_file,
        "int adjust_if(int value, int flag) { if (flag) { value = value + 1; } else { value = value + ~0; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "adjust_if");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit simple if from real clang AST");
    assert!(rust.contains("pub fn adjust_if(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_if_without_braces_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-if-without-braces");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_if_no_braces.c");
    fs::write(
        &source_file,
        "int adjust_if_no_braces(int value, int flag) { if (flag) value = value + 1; else value = value + ~0; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "adjust_if_no_braces",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { value, .. }] if matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { value, .. }] if matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit no-brace if from real clang AST");
    assert!(rust.contains("pub fn adjust_if_no_braces(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-without-braces", &rust);
}

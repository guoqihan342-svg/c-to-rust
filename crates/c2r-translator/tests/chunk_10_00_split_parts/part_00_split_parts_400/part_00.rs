#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_do_while_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-do-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("do_countdown.c");
    fs::write(
        &source_file,
        "int do_countdown(int value) { do { value = value - 1; } while (value); return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "do_countdown");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::DoWhile { body, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!(
            "expected do-while followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(body.as_slice(), [IrStmt::Assign { .. }]));

    let rust = emit_rust_from_ir(function).expect("emit typed IR do-while from real clang AST");
    assert!(rust.contains("pub fn do_countdown(mut value: i32) -> i32"));
    assert!(rust.contains("loop {"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust.contains("if !(value != 0i32) {"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-do-while", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_typed_ir_for_missing_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-missing-condition");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_for_missing_condition.c");
    fs::write(
        &source_file,
        "int bad_for_missing_condition(int limit) { int total = 0; for (int i = 0; ; i++) { total = total + i; if (total > limit) { return total; } } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_for_missing_condition",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert!(
        report
            .errors
            .iter()
            .any(|error| error.message.contains("ForStmt without condition")),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_missing_step_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-missing-step");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sum_without_step.c");
    fs::write(
        &source_file,
        "int sum_without_step(int limit) { int total = 0; for (int i = 0; i < limit;) { total = total + i; i = i + 1; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "sum_without_step");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { .. }, IrStmt::For { step, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected declaration, for, and return, got {:?}",
            function.body
        );
    };
    assert!(step.is_none(), "missing step must lower to None: {step:?}");
    let emitted = emit_rust_from_ir(function).expect("emit real clang missing-step for loop");
    assert!(emitted.rust.contains("pub fn sum_without_step"));
    assert_rust_snippet_compiles("typed-ir-real-clang-for-missing-step", &emitted.rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_multi_var_decl_init_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-multi-var-decl-init");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sum_pair_for.c");
    fs::write(
        &source_file,
        "int sum_pair_for(int limit) { int total = 0; for (int i = 0, j = 0; i < limit; i++) { total = total + i + j; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "sum_pair_for");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, .. }, IrStmt::For {
        init, step, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected total declaration, for loop, and return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "total");
    assert!(
        matches!(
            init.as_slice(),
            [IrStmt::Decl { name: first, .. }, IrStmt::Decl { name: second, .. }]
                if first == "i" && second == "j"
        ),
        "expected for init declarations i and j, got {init:?}"
    );
    assert!(matches!(step.as_deref(), Some(IrStmt::Assign { .. })));
    assert!(matches!(body.as_slice(), [IrStmt::Assign { .. }]));

    let emitted = emit_rust_from_ir(function)
        .expect("emit for loop with multi declaration initializer from real clang AST");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn sum_pair_for(limit: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let mut total: i32 = 0i32;"), "{rust}");
    assert!(rust.contains("let mut i: i32 = 0i32;"), "{rust}");
    assert!(rust.contains("let mut j: i32 = 0i32;"), "{rust}");
    assert!(rust.contains("while (i < limit) {"), "{rust}");
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\").checked_add(j).expect(\"signed addition overflow\");"), "{rust}");
    assert!(
        rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert!(rust.contains("return total;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-for-multi-var-decl-init", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_prefix_increment_step_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-prefix-step");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sum_prefix_for.c");
    fs::write(
        &source_file,
        "int sum_prefix_for(int limit) { int total = 0; for (int i = 0; i < limit; ++i) { total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "sum_prefix_for");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { .. }, IrStmt::For { step, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert!(matches!(step.as_deref(), Some(IrStmt::Assign { .. })));

    let rust = emit_rust_from_ir(function).expect("emit prefix increment for step");
    assert!(rust.contains("pub fn sum_prefix_for(limit: i32) -> i32"));
    assert!(rust.contains("while (i < limit) {"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-for-prefix-inc-step", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_prefix_decrement_step_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-prefix-dec-step");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sum_prefix_down_for.c");
    fs::write(
        &source_file,
        "int sum_prefix_down_for(int limit) { int total = 0; for (int i = limit; i > 0; --i) { total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "sum_prefix_down_for",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { .. }, IrStmt::For { step, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert!(matches!(step.as_deref(), Some(IrStmt::Assign { .. })));

    let rust = emit_rust_from_ir(function).expect("emit prefix decrement for step");
    assert!(rust.contains("pub fn sum_prefix_down_for(limit: i32) -> i32"));
    assert!(rust.contains("while (i > 0i32) {"));
    assert!(rust.contains("i = i.checked_sub(1i32).expect(\"signed subtraction overflow\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-for-prefix-dec-step", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_standalone_inc_dec_statements_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-standalone-inc-dec-statements");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("standalone_inc_dec.c");
    fs::write(
        &source_file,
        "int standalone_inc_dec(int value) { value++; ++value; value--; --value; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "standalone_inc_dec");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected four inc/dec assignments followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit standalone inc/dec statements");
    assert!(rust.contains("pub fn standalone_inc_dec(mut value: i32) -> i32"));
    assert_eq!(
        rust.matches("value = value.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2
    );
    assert_eq!(
        rust.matches("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
            .count(),
        2
    );
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-standalone-inc-dec", &rust);
}

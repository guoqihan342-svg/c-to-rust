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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_record_field_inc_dec_statements_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-record-field-inc-dec-statements");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("record_field_inc_dec.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint bump_point_x(struct point p) { p.x++; ++p.x; p.x--; --p.x; return p.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bump_point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected four record field inc/dec assignments followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit record field inc/dec statements");
    assert!(rust.contains("pub fn bump_point_x(mut p: Point) -> i32"));
    assert_eq!(
        rust.matches("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2
    );
    assert_eq!(
        rust.matches("p.x = p.x.checked_sub(1i32).expect(\"signed subtraction overflow\");")
            .count(),
        2
    );
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-record-field-inc-dec", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_mutable_record_pointer_field_inc_dec_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mutable-record-pointer-field-inc-dec");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_record_pointer_field_inc_dec.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nvoid bump_point_x(struct point *p) { p->x++; ++p->x; p->x--; --p->x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bump_point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Assign { .. }, IrStmt::Assign { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected four mutable record pointer field inc/dec assignments, got {:?}",
            function.body
        );
    };

    let emitted = emit_rust_from_ir(function)
        .expect("emit mutable record pointer field inc/dec statement from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn bump_point_x(mut p: &mut Point)"),
        "{rust}"
    );
    assert_eq!(
        rust.matches("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2
    );
    assert_eq!(
        rust.matches("p.x = p.x.checked_sub(1i32).expect(\"signed subtraction overflow\");")
            .count(),
        2
    );
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-mutable-record-pointer-field-inc-dec",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_record_field_inc_dec_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-record-field-inc-dec-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_record_field_inc_dec_return.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint bad_record_field_inc_dec_return(struct point p) { return p.x++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_record_field_inc_dec_return",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error =
        emit_rust_from_ir(function).expect_err("record field inc/dec return must fail closed");
    assert!(error.reason.contains("stmt[0].return expr"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_record_field_inc_dec_for_step_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-record-field-inc-dec-for-step");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("record_field_inc_dec_for_step.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint record_field_inc_dec_for_step(struct point p, int limit) { for (int i = 0; i < limit; p.x++) { i++; } return p.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "record_field_inc_dec_for_step",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir(function)
        .expect("emit record field inc/dec for step from real clang AST");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn record_field_inc_dec_for_step(mut p: Point, limit: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-record-field-inc-dec-for-step", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_add_one_ast_with_leading_stmt(function_name: &str, stmt: Value) -> Value {
    let mut ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/add_one_ast.json"))
            .expect("add-one fixture JSON");
    ast["inner"][0]["name"] = serde_json::json!(function_name);
    ast["inner"][0]["inner"][1]["inner"]
        .as_array_mut()
        .expect("function compound body")
        .insert(0, stmt);
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_ignores_exact_null_stmt_in_compound_without_clang_and_runs() {
    let function_name = "increment_after_empty_statement";
    let ast = renamed_add_one_ast_with_leading_stmt(
        function_name,
        serde_json::json!({
            "kind": "NullStmt",
            "range": { "begin": {}, "end": {} }
        }),
    );

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("ignore exact NullStmt in a CompoundStmt without invoking clang");
    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [IrStmt::Return { .. }]
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed function after ignoring NullStmt");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn increment_after_empty_statement(value: i32) -> i32"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-exact-null-stmt",
        rust,
        "assert_eq!(increment_after_empty_statement(41i32), 42i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_treats_single_statement_null_stmt_as_empty_body_without_clang_and_runs() {
    let function_name = "increment_after_empty_branch";
    let ast = renamed_add_one_ast_with_leading_stmt(
        function_name,
        serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                int_read_ast("value", "ParmVarDecl"),
                { "kind": "NullStmt" }
            ]
        }),
    );

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("treat a direct NullStmt body as an empty body without invoking clang");
    let [IrStmt::If {
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected empty if body followed by return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert!(then_body.is_empty(), "{then_body:?}");
    assert!(else_body.is_empty(), "{else_body:?}");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed function with an empty single-statement body");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-single-null-stmt-body",
        &emitted.rust,
        "assert_eq!(increment_after_empty_branch(41i32), 42i32);",
    );
}

#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_ast_single_statement_null_stmt_match_is_exact_and_draft_stays_empty() {
    let function_name = "reject_similar_empty_branch";
    let slice_id = "reject-similar-empty-branch";
    let ast = renamed_add_one_ast_with_leading_stmt(
        function_name,
        serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                int_read_ast("value", "ParmVarDecl"),
                { "kind": "NullStmtSuffix" }
            ]
        }),
    );

    assert_no_clang_ast_refusal_writes_empty_draft(&ast, function_name, slice_id);
}

#[cfg(feature = "clang-lowering-report")]
fn assert_no_clang_ast_refusal_writes_empty_draft(
    ast: &Value,
    function_name: &str,
    slice_id: &str,
) {
    let fixture_dir = unique_out_dir(&format!("{slice_id}-ast"));
    fs::create_dir_all(&fixture_dir).unwrap();
    let fixture_file = fixture_dir.join("frontend-boundary.json");
    fs::write(&fixture_file, serde_json::to_vec_pretty(ast).unwrap()).unwrap();

    let source_file = format!("{function_name}.c");
    let mut build_profile = profile(true);
    build_profile.clang_ast_fixture = Some(fixture_file.to_string_lossy().into_owned());
    let spec = SliceSpec {
        target_id: "frontend-boundary".to_string(),
        slice_id: slice_id.to_string(),
        source_commit: "1234567".to_string(),
        function_name: function_name.to_string(),
        c_source: format!("int {function_name}(int value) {{ value ? value : 0; return value; }}"),
        fixture_hash: "fixture-sha".to_string(),
        source_root: Some(".".to_string()),
        source_file: Some(source_file.clone()),
        source_file_hashes: std::collections::BTreeMap::from([(
            source_file,
            "source-file-sha".to_string(),
        )]),
        build_profile,
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir(slice_id);

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let draft = fs::read_to_string(out_dir.join(format!("l3-{slice_id}-rust-draft.rs"))).unwrap();
    assert!(draft.is_empty(), "{draft}");
    let report = json_file(out_dir.join(format!("l3-{slice_id}-clang-lowering-report.json")));
    assert_eq!(
        report["lowering_report"]["frontend"],
        "clang_ast_json_fixture"
    );
    assert_eq!(report["lowering_report"]["status"], "blocked");
    assert!(
        report["lowering_report"]["errors"]
            .as_array()
            .expect("lowering errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_clang_stmt"),
        "{report:?}"
    );

    fs::remove_dir_all(out_dir).unwrap();
    fs::remove_dir_all(fixture_dir).unwrap();
}

#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_ast_null_stmt_match_is_exact_and_unknown_stmt_drafts_stay_empty() {
    for (kind, function_name, slice_id) in [
        (
            "NullStmtSuffix",
            "reject_similar_empty_statement",
            "reject-similar-empty-statement",
        ),
        (
            "ConditionalOperator",
            "reject_unknown_expression_statement",
            "reject-unknown-expression-statement",
        ),
    ] {
        let ast = renamed_add_one_ast_with_leading_stmt(
            function_name,
            serde_json::json!({ "kind": kind, "type": { "qualType": "int" } }),
        );
        assert_no_clang_ast_refusal_writes_empty_draft(&ast, function_name, slice_id);
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn int_literal_ast(value: i32) -> Value {
    serde_json::json!({
        "kind": "IntegerLiteral",
        "type": { "qualType": "int" },
        "value": value.to_string()
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn int_decl_ref_ast(name: &str, decl_kind: &str) -> Value {
    serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "int" },
        "referencedDecl": { "kind": decl_kind, "name": name }
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn int_read_ast(name: &str, decl_kind: &str) -> Value {
    serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "int" },
        "inner": [int_decl_ref_ast(name, decl_kind)]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn int_binary_ast(opcode: &str, lhs: Value, rhs: Value) -> Value {
    serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": opcode,
        "type": { "qualType": "int" },
        "inner": [lhs, rhs]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn int_assignment_ast(name: &str, value: Value) -> Value {
    int_binary_ast("=", int_decl_ref_ast(name, "VarDecl"), value)
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_missing_step_for_ast(function_name: &str) -> Value {
    serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "FunctionDecl",
            "name": function_name,
            "type": { "qualType": "int (int)" },
            "inner": [
                {
                    "kind": "ParmVarDecl",
                    "name": "limit",
                    "type": { "qualType": "int" }
                },
                {
                    "kind": "CompoundStmt",
                    "inner": [
                        {
                            "kind": "DeclStmt",
                            "inner": [{
                                "kind": "VarDecl",
                                "name": "total",
                                "type": { "qualType": "int" },
                                "init": "c",
                                "inner": [int_literal_ast(0)]
                            }]
                        },
                        {
                            "kind": "ForStmt",
                            "inner": [
                                {
                                    "kind": "DeclStmt",
                                    "inner": [{
                                        "kind": "VarDecl",
                                        "name": "i",
                                        "type": { "qualType": "int" },
                                        "init": "c",
                                        "inner": [int_literal_ast(0)]
                                    }]
                                },
                                {},
                                int_binary_ast(
                                    "<",
                                    int_read_ast("i", "VarDecl"),
                                    int_read_ast("limit", "ParmVarDecl")
                                ),
                                {},
                                {
                                    "kind": "CompoundStmt",
                                    "inner": [
                                        int_assignment_ast(
                                            "i",
                                            int_binary_ast(
                                                "+",
                                                int_read_ast("i", "VarDecl"),
                                                int_literal_ast(1)
                                            )
                                        ),
                                        {
                                            "kind": "IfStmt",
                                            "inner": [
                                                int_binary_ast(
                                                    "<",
                                                    int_read_ast("i", "VarDecl"),
                                                    int_read_ast("limit", "ParmVarDecl")
                                                ),
                                                { "kind": "ContinueStmt" }
                                            ]
                                        },
                                        int_assignment_ast(
                                            "total",
                                            int_binary_ast(
                                                "+",
                                                int_read_ast("total", "VarDecl"),
                                                int_read_ast("i", "VarDecl")
                                            )
                                        )
                                    ]
                                }
                            ]
                        },
                        {
                            "kind": "ReturnStmt",
                            "inner": [int_read_ast("total", "VarDecl")]
                        }
                    ]
                }
            ]
        }]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn missing_step_for_inner(ast: &mut Value) -> &mut Vec<Value> {
    ast["inner"][0]["inner"][1]["inner"][1]["inner"]
        .as_array_mut()
        .expect("ForStmt inner slots")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_lowers_missing_step_for_to_none_without_clang_and_runs() {
    let function_name = "accumulate_without_step";
    let ast = renamed_missing_step_for_ast(function_name);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower for loop with a condition and an empty step slot");
    let [IrStmt::Decl { .. }, IrStmt::For { step, .. }, IrStmt::Return { .. }] =
        lowered.function_ir.body.as_slice()
    else {
        panic!(
            "unexpected missing-step function body: {:?}",
            lowered.function_ir.body
        );
    };
    assert!(step.is_none(), "missing step must stay None, got {step:?}");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit for loop through the existing no-step path");
    let rust = &emitted.rust;
    let body_increment = "i = i.checked_add(1i32).expect(\"signed addition overflow\");";
    assert_eq!(rust.matches(body_increment).count(), 1, "{rust}");
    assert!(rust.contains("continue;"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-for-missing-step",
        rust,
        "assert_eq!(accumulate_without_step(0i32), 0i32);\n\
         assert_eq!(accumulate_without_step(1i32), 1i32);\n\
         assert_eq!(accumulate_without_step(4i32), 4i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_missing_step_for_keeps_adjacent_boundaries_fail_closed() {
    let function_name = "bounded_missing_step_loop";
    let base = renamed_missing_step_for_ast(function_name);
    let mut cases = Vec::new();

    let mut missing_condition = base.clone();
    missing_step_for_inner(&mut missing_condition)[2] = serde_json::json!({});
    cases.push((
        "missing condition",
        missing_condition,
        "unsupported_clang_stmt",
        "ForStmt without condition",
    ));

    let mut condition_variable = base.clone();
    missing_step_for_inner(&mut condition_variable)[1] =
        serde_json::json!({ "kind": "VarDecl", "name": "guard" });
    cases.push((
        "condition variable",
        condition_variable,
        "unsupported_clang_stmt",
        "ForStmt condition variable",
    ));

    let mut unsupported_init = base.clone();
    missing_step_for_inner(&mut unsupported_init)[0] = serde_json::json!({ "kind": "CallExpr" });
    cases.push((
        "unsupported init",
        unsupported_init,
        "unsupported_clang_stmt",
        "ForStmt init CallExpr",
    ));

    let mut unsupported_condition = base.clone();
    missing_step_for_inner(&mut unsupported_condition)[2] = serde_json::json!({
        "kind": "MysteryExpr",
        "type": { "qualType": "int" }
    });
    cases.push((
        "unsupported condition",
        unsupported_condition,
        "unsupported_clang_expr",
        "MysteryExpr",
    ));

    let mut unsupported_body = base;
    missing_step_for_inner(&mut unsupported_body)[4] = serde_json::json!({
        "kind": "CompoundStmt",
        "inner": [{ "kind": "MysteryStmt" }]
    });
    cases.push((
        "unsupported body",
        unsupported_body,
        "unsupported_clang_stmt",
        "MysteryStmt",
    ));

    for (label, ast, expected_kind, expected_message) in cases {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err(label);
        assert_eq!(error.kind, expected_kind, "{label}: {error:?}");
        assert!(
            error.message.contains(expected_message),
            "{label}: {error:?}"
        );
    }
}

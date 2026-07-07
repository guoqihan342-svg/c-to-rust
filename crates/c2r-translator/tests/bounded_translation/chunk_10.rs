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
fn clang_ast_dump_rejects_typed_ir_for_missing_step_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-missing-step");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_for_missing_step.c");
    fs::write(
        &source_file,
        "int bad_for_missing_step(int limit) { int total = 0; for (int i = 0; i < limit;) { total = total + i; i = i + 1; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_for_missing_step",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert!(
        report
            .errors
            .iter()
            .any(|error| error.message.contains("ForStmt without step")),
        "{:?}",
        report.errors
    );
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
fn clang_ast_dump_rejects_record_field_inc_dec_for_step_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-record-field-inc-dec-for-step");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_record_field_inc_dec_for_step.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint bad_record_field_inc_dec_for_step(struct point p, int limit) { for (int i = 0; i < limit; p.x++) { i++; } return p.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_record_field_inc_dec_for_step",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert!(
        report.errors.iter().any(|error| error
            .message
            .contains("record field targets are unsupported outside standalone statements")),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_nested_record_field_inc_dec_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-record-field-inc-dec");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_nested_record_field_inc_dec.c");
    fs::write(
        &source_file,
        "struct inner { int x; };\nstruct outer { struct inner inner; int y; };\nint bad_nested_record_field_inc_dec(struct outer p) { p.inner.x++; return p.inner.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_nested_record_field_inc_dec",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert!(
        report.errors.iter().any(|error| error
            .message
            .contains("record field target must have a direct record variable base")),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_static_const_integer_array_global_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-global-array-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table_emit.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[4] = { 1U, 2U, 0xEDB88320U, 4U };\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit global table from clang typed IR");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(emitted
        .rust
        .contains("const TABLE: [u32; 4] = [1u32, 2u32, 3988292384u32, 4u32];"));
    assert!(emitted
        .rust
        .contains("pub fn read_global_table(idx: u32) -> u32"));
    assert!(emitted.rust.contains("return TABLE[idx as usize];"));
    assert!(!emitted.rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("clang_real_global_array_emit", &emitted.rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_records_static_const_incomplete_array_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-incomplete-global-array-init");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_incomplete_global_table_init.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[] = { 1U, 2U, 0xEDB88320U, 4U };\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert_eq!(report.globals.len(), 1);
    let global = &report.globals[0];
    assert_eq!(global.name, "table");
    assert!(matches!(
        global.ty.kind,
        IrTypeKind::Array { len: Some(4), .. }
    ));
    assert_eq!(
        global.init,
        IrGlobalInit::IntegerArray(vec![1, 2, 0xEDB8_8320, 4])
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_does_not_synthesize_uninitialized_static_const_global_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-uninitialized-global-array");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_uninitialized_global_table.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[4];\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.globals.is_empty());
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect_err("uninitialized global table must not be synthesized");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("index base table is not declared"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_bitand_array_index_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-bitand-array-index");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_index.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_index(uint32_t crc, uint32_t idx) { return table[(crc ^ idx) & 0xff]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_index");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        rhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
    assert!(matches!(
        without_implicit_cast(rhs.as_ref()),
        IrExpr::LitInt { value: 255, .. }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_bitxor_bitnot_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-bitxor-bitnot-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_not.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_not(uint32_t crc) { crc = crc ^ ~0U; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_not");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected bitxor assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        lhs,
        rhs,
        ..
    } = value
    else {
        panic!("expected bitxor assignment value, got {value:?}");
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand,
        ..
    } = rhs.as_ref()
    else {
        panic!("expected bitnot rhs, got {rhs:?}");
    };
    assert!(matches!(operand.as_ref(), IrExpr::LitInt { value: 0, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_parenthesized_bitxor_bitnot_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-parenthesized-bitxor-bitnot-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_not_paren.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_not_paren(uint32_t crc) { crc = (crc ^ ~0U); return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_not_paren");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { value, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!(
            "expected parenthesized bitxor assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(
        value,
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_simple_while_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-simple-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_while(uint32_t crc) { while (crc) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_while");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "crc")
                && matches!(value, IrExpr::Var { name, .. } if name == "crc")
    ));
}

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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_positive.c");
    fs::write(
        &source_file,
        "int adjust_positive(int value) { if (value > 0) { value = value + 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "adjust_positive");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::Gt, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected comparison if followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit comparison if from real clang AST");
    assert!(rust.contains("pub fn adjust_positive(mut value: i32) -> i32"));
    assert!(rust.contains("if (value > 0i32) {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("positive_as_int.c");
    fs::write(
        &source_file,
        "int positive_as_int(int value) { return value > 0; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "positive_as_int");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary {
            op: IrBinOp::Gt, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected comparison return, got {:?}", function.body);
    };

    let rust = emit_rust_from_ir(function).expect("emit comparison return from real clang AST");
    assert!(rust.contains("pub fn positive_as_int(value: i32) -> i32"));
    assert!(rust.contains("return (if (value > 0i32) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-return-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_null_pointer_comparison_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-null-pointer-comparison-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("has_values.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\nint has_values(const int *values) { return values != NULL; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "has_values");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Neq,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected null pointer comparison return, got {:?}",
            function.body
        );
    };
    assert!(matches!(rhs.as_ref(), IrExpr::NullPtr { .. }));

    let rust = emit_rust_from_ir(function)
        .expect("emit null pointer comparison return from real clang AST");
    assert!(rust.contains("pub fn has_values(values: Option<&[i32]>) -> i32"));
    assert!(rust.contains("return (if values.is_some() { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-return-null-pointer-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_record_null_pointer_comparison_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-record-null-pointer-comparison-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("has_point.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\n\
         struct point { int x; };\n\
         int has_point(const struct point *p) { return p != NULL; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "has_point");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Neq,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected record null pointer comparison return, got {:?}",
            function.body
        );
    };
    assert!(matches!(rhs.as_ref(), IrExpr::NullPtr { .. }));

    let emitted = emit_rust_from_ir(function)
        .expect("emit record null pointer comparison return from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn has_point(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return (if p.is_some() { 1i32 } else { 0i32 });"),
        "{rust}"
    );
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-return-record-null-pointer-comparison",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("cmp_init.c");
    fs::write(
        &source_file,
        "int cmp_init(int left, int right) { int out = left == right; return out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "cmp_init");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Binary {
            op: IrBinOp::Eq, ..
        }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected comparison decl initializer followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit comparison decl initializer from real clang AST");
    assert!(rust.contains("pub fn cmp_init(left: i32, right: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if (left == right) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-decl-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_assignment_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("cmp_assign.c");
    fs::write(
        &source_file,
        "int cmp_assign(int left, int right) { left = left != right; return left; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "cmp_assign");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Binary {
            op: IrBinOp::Neq, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected comparison assignment followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit comparison assignment from real clang AST");
    assert!(rust.contains("pub fn cmp_assign(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains("left = (if (left != right) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return left;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-assign-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_conditional_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-conditional-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pick.c");
    fs::write(
        &source_file,
        "int pick(int flag, int left, int right) { return flag ? left : right; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "pick");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Conditional { .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected conditional return, got {:?}", function.body);
    };

    let rust = emit_rust_from_ir(function).expect("emit conditional return from real clang AST");
    assert!(rust.contains("pub fn pick(flag: i32, left: i32, right: i32) -> i32"));
    assert!(rust.contains("return (if flag != 0i32 { left } else { right });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-conditional-return", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_conditional_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-conditional-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pick_init.c");
    fs::write(
        &source_file,
        "int pick_init(int flag, int left, int right) { int out = flag ? left : right; return out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "pick_init");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Conditional { .. }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected conditional decl initializer followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit conditional decl initializer from real clang AST");
    assert!(rust.contains("pub fn pick_init(flag: i32, left: i32, right: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if flag != 0i32 { left } else { right });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-conditional-decl", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_conditional_assignment_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-conditional-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pick_assign.c");
    fs::write(
        &source_file,
        "int pick_assign(int flag, int value, int fallback) { value = flag ? value : fallback; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "pick_assign");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Conditional { .. },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected conditional assignment followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit conditional assignment from real clang AST");
    assert!(rust.contains("pub fn pick_assign(flag: i32, mut value: i32, fallback: i32) -> i32"));
    assert!(rust.contains("value = (if flag != 0i32 { value } else { fallback });"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-conditional-assign", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_conditional_branch_integral_cast_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-conditional-cast");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("choose_u32.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t choose_u32(uint32_t flag, uint32_t value) { return flag ? value : 2; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "choose_u32");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Conditional { else_expr, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned conditional return, got {:?}",
            function.body
        );
    };
    assert!(matches!(
        else_expr.as_ref(),
        IrExpr::Cast { implicit: true, .. }
    ));

    let rust =
        emit_rust_from_ir(function).expect("emit unsigned conditional return from real clang AST");
    assert!(rust.contains("pub fn choose_u32(flag: u32, value: u32) -> u32"));
    assert!(rust.contains("return (if flag != 0u32 { value } else { (2i32 as u32) });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-unsigned-conditional-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_binary_conditional_operator_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-binary-conditional");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_gnu_conditional.c");
    fs::write(
        &source_file,
        "int bad_gnu_conditional(int value, int fallback) { return value ?: fallback; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_gnu_conditional",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert_eq!(
        report.errors.first().map(|error| error.kind.as_str()),
        Some("unsupported_clang_expr")
    );
    assert!(
        report
            .errors
            .first()
            .map(|error| error.message.contains("BinaryConditionalOperator"))
            .unwrap_or(false),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_assignment_rhs_integral_cast_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-assignment-rhs-cast");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("set_unsigned_one.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t set_unsigned_one(uint32_t value) { value = 1; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "set_unsigned_one");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Cast { implicit: true, .. },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned assignment RHS cast followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit unsigned assignment RHS integral cast");
    assert!(rust.contains("pub fn set_unsigned_one(mut value: u32) -> u32"));
    assert!(rust.contains("value = (1i32 as u32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-assign-rhs-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_decl_and_return_integral_casts_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-decl-return-casts");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("unsigned_decl_return.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t unsigned_decl_return(void) { uint32_t value = 1; return 2; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "unsigned_decl_return",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Cast { implicit: true, .. }),
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Cast { implicit: true, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned decl initializer and return casts, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit unsigned decl initializer and return casts");
    assert!(rust.contains("pub fn unsigned_decl_return() -> u32"));
    assert!(rust.contains("let mut value: u32 = (1i32 as u32);"));
    assert!(rust.contains("return (2i32 as u32);"));
    assert_rust_snippet_compiles("typed-ir-real-clang-decl-return-casts", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("is_zero.c");
    fs::write(
        &source_file,
        "int is_zero(int value) { if (!value) { return 1; } return 0; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "is_zero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition: IrExpr::Unary {
            op: IrUnOp::Not, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected logical not if followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit logical not if from real clang AST");
    assert!(rust.contains("pub fn is_zero(value: i32) -> i32"));
    assert!(rust.contains("if value == 0i32 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_short_circuit_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-short-circuit-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("both_nonzero.c");
    fs::write(
        &source_file,
        "int both_nonzero(int left, int right) { if (left && right) { return 1; } return 0; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "both_nonzero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::LogAnd,
            ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected short-circuit if followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit short-circuit if from real clang AST");
    assert!(rust.contains("pub fn both_nonzero(left: i32, right: i32) -> i32"));
    assert!(rust.contains("if (left != 0i32 && right != 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-short-circuit", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_short_circuit_value_positions_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-short-circuit-values");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("short_circuit_values.c");
    fs::write(
        &source_file,
        "int short_circuit_values(int left, int right) { int out = left || right; left = left && (right > 0); return left || out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "short_circuit_values",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Binary {
            op: IrBinOp::LogOr, ..
        }),
        ..
    }, IrStmt::Assign {
        value: IrExpr::Binary {
            op: IrBinOp::LogAnd,
            ..
        },
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Binary {
            op: IrBinOp::LogOr, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected short-circuit decl, assignment, and return values, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit short-circuit values from real clang AST");
    assert!(rust.contains("pub fn short_circuit_values(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains(
        "let mut out: i32 = (if (left != 0i32 || right != 0i32) { 1i32 } else { 0i32 });"
    ));
    assert!(rust.contains("left = (if (left != 0i32 && (right > 0i32)) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return (if (left != 0i32 || out != 0i32) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-short-circuit-values", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_scalar_compound_assignment_family_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-compound-assignment-family");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("compound_family.c");
    fs::write(
        &source_file,
        "int compound_family(int value) { value += 1; value -= 2; value *= 3; value /= 4; value %= 5; value &= 7; value |= 8; value ^= 9; value <<= 1; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "compound_family");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert_eq!(function.body.len(), 10, "{:?}", function.body);
    for (stmt, expected_op) in function.body.iter().take(9).zip([
        IrBinOp::Add,
        IrBinOp::Sub,
        IrBinOp::Mul,
        IrBinOp::Div,
        IrBinOp::Mod,
        IrBinOp::BitAnd,
        IrBinOp::BitOr,
        IrBinOp::BitXor,
        IrBinOp::Shl,
    ]) {
        let IrStmt::Assign { target, value, .. } = stmt else {
            panic!("expected desugared compound assignment, got {stmt:?}");
        };
        assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
        assert!(
            matches!(value, IrExpr::Binary { op, .. } if *op == expected_op),
            "{value:?}"
        );
    }

    let rust =
        emit_rust_from_ir(function).expect("emit scalar compound assignments from real clang AST");
    assert!(rust.contains("pub fn compound_family(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(
        rust.contains("value = value.checked_sub(2i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust
        .contains("value = value.checked_mul(3i32).expect(\"signed multiplication overflow\");"));
    assert!(rust.contains(
        "value = value.checked_div(4i32).expect(\"division by zero or signed overflow\");"
    ));
    assert!(rust.contains(
        "value = value.checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"
    ));
    assert!(rust.contains("value = (value & 7i32);"));
    assert!(rust.contains("value = (value | 8i32);"));
    assert!(rust.contains("value = (value ^ 9i32);"));
    assert!(rust.contains("value = value.checked_shl(core::convert::TryFrom::try_from(1i32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-compound-family", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_compound_assignment_integer_promotion_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-compound-assignment-integer-promotion");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("inc8.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t compound_assignment_integer_promotion(uint8_t value) { value += 1; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "compound_assignment_integer_promotion",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected promoted compound assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
    let IrExpr::Cast {
        target: cast_target,
        expr,
        implicit: true,
        ..
    } = value
    else {
        panic!("expected compound assignment final cast, got {value:?}");
    };
    assert!(matches!(
        &cast_target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
    assert!(matches!(
        expr.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Add,
            ty,
            ..
        } if matches!(&ty.kind, IrTypeKind::Integer { signed: true, width: 32 })
    ));

    let rust =
        emit_rust_from_ir(function).expect("emit promoted compound assignment from real clang AST");
    assert!(rust.contains("pub fn compound_assignment_integer_promotion(mut value: u8) -> u8"));
    assert!(rust.contains(
        "value = ((value as i32).checked_add(1i32).expect(\"signed addition overflow\") as u8);"
    ));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-compound-promotion", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("is_zero_value.c");
    fs::write(
        &source_file,
        "int is_zero_value(int value) { return !value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "is_zero_value");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Unary {
            op: IrUnOp::Not, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected logical not return, got {:?}", function.body);
    };

    let rust = emit_rust_from_ir(function).expect("emit logical not return from real clang AST");
    assert!(rust.contains("pub fn is_zero_value(value: i32) -> i32"));
    assert!(rust.contains("return (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-return-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("init_is_zero.c");
    fs::write(
        &source_file,
        "int init_is_zero(int value) { int out = !value; return out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "init_is_zero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Unary {
            op: IrUnOp::Not, ..
        }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected logical not decl initializer followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit logical not decl initializer from real clang AST");
    assert!(rust.contains("pub fn init_is_zero(value: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-decl-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_assignment_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("normalize_zero.c");
    fs::write(
        &source_file,
        "int normalize_zero(int value) { value = !value; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "normalize_zero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Unary {
            op: IrUnOp::Not, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected logical not assignment followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit logical not assignment from real clang AST");
    assert!(rust.contains("pub fn normalize_zero(mut value: i32) -> i32"));
    assert!(rust.contains("value = (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-assign-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_comparison_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-comparison-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_unsigned_positive.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t adjust_unsigned_positive(uint32_t value) { if (value > 0) { value = value + 1U; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "adjust_unsigned_positive",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition:
            IrExpr::Binary {
                op: IrBinOp::Gt,
                rhs,
                ..
            },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned comparison if followed by return, got {:?}",
            function.body
        );
    };
    assert!(
        matches!(rhs.as_ref(), IrExpr::Cast { implicit: true, .. }),
        "expected clang integral cast on unsigned comparison literal, got {rhs:?}"
    );

    let rust =
        emit_rust_from_ir(function).expect("emit unsigned comparison if from real clang AST");
    assert!(rust.contains("pub fn adjust_unsigned_positive(mut value: u32) -> u32"));
    assert!(rust.contains("if (value > (0i32 as u32)) {"));
    assert!(rust.contains("value = value.wrapping_add(1u32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-unsigned-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_signed_char_binary_promotion_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-signed-char-binary-promotion");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("signed_char_add_one.c");
    fs::write(
        &source_file,
        "int signed_char_add_one(signed char value) { return value + 1; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "signed_char_add_one",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary { lhs, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected signed char binary promotion return, got {:?}",
            function.body
        );
    };
    assert!(
        matches!(lhs.as_ref(), IrExpr::Cast { implicit: true, .. }),
        "expected clang integral promotion cast on signed char lhs, got {lhs:?}"
    );

    let rust = emit_rust_from_ir(function).expect("emit signed char binary promotion");
    assert!(rust.contains("pub fn signed_char_add_one(value: i8) -> i32"));
    assert!(rust
        .contains("return (value as i32).checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-signed-char-promotion", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_postfix_increment_if_condition_in_scalar_emitter_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-if-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_if_postinc.c");
    fs::write(
        &source_file,
        "int bad_if_postinc(int value) { if (value++) { value = value; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_if_postinc");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error =
        emit_rust_from_ir(function).expect_err("postfix increment if condition must fail closed");
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_postfix_decrement_while_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-decrement-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while_size.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t crc_while_size(uint32_t crc, size_t size) { while (size--) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_while_size");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ..
    } = condition
    else {
        panic!("expected postfix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_postfix_decrement_while_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-decrement-while-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_while_size.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\nint bad_while_size(int value, size_t size) { while (size--) { value = value; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_while_size");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit postfix decrement while condition");
    assert!(rust.contains("pub fn bad_while_size(mut value: i32, mut size: usize) -> i32"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("let size_before_dec0: usize = size;"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size_before_dec0 == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("value = value;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-postfix-decrement-while", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_prefix_decrement_while_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-decrement-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while_prefix_size.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t crc_while_prefix_size(uint32_t crc, size_t size) { while (--size) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "crc_while_prefix_size",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit prefix decrement while condition");
    assert!(rust.contains("pub fn crc_while_prefix_size(mut crc: u32, mut size: usize) -> u32"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("crc = crc;"));
    assert!(rust.contains("return crc;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-prefix-decrement-while", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_prefix_increment_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-increment-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("prefix_return.c");
    fs::write(
        &source_file,
        "int prefix_return(int value) { return ++value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "prefix_return");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit prefix increment return value");
    assert!(rust.contains("pub fn prefix_return(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-prefix-increment-return",
        &rust,
        "    assert_eq!(prefix_return(5), 6);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_postfix_increment_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("postfix_decl.c");
    fs::write(
        &source_file,
        "int postfix_decl(int value) { int out = value++; return out + value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "postfix_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit postfix increment decl initializer");
    assert!(rust.contains("pub fn postfix_decl(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = post_inc_value;"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-postfix-increment-decl",
        &rust,
        "    assert_eq!(postfix_decl(5), 11);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_prefix_increment_call_argument_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-increment-call-arg");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("prefix_call_arg.c");
    fs::write(
        &source_file,
        "int helper(int value) { return value * 2; }\nint prefix_call_arg(int value) { return helper(++value); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "prefix_call_arg");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit prefix increment call argument");
    assert!(rust.contains("pub fn prefix_call_arg(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(value);"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-prefix-increment-call-arg",
        &format!(
            "fn helper(value: i32) -> i32 {{ value * 2 }}\n{}",
            rust.rust
        ),
        "    assert_eq!(prefix_call_arg(5), 12);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_postfix_increment_call_argument_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-call-arg");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("postfix_call_arg.c");
    fs::write(
        &source_file,
        "int helper(int value) { return value * 2; }\nint postfix_call_arg(int value) { return helper(value++); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "postfix_call_arg");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit postfix increment call argument");
    assert!(rust.contains("pub fn postfix_call_arg(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(post_inc_value);"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-postfix-increment-call-arg",
        &format!(
            "fn helper(value: i32) -> i32 {{ value * 2 }}\n{}",
            rust.rust
        ),
        "    assert_eq!(postfix_call_arg(5), 10);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_prefix_increment_deref_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-increment-deref");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_prefix_inc.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_prefix_inc(const uint8_t *p) { return *++p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "read_byte_prefix_inc",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert_eq!(
        report.errors.first().map(|error| error.kind.as_str()),
        Some("unsupported_clang_expr")
    );
    assert!(
        report
            .errors
            .first()
            .map(|error| {
                error
                    .message
                    .contains("deref pointer cannot use prefix increment/decrement value semantics")
            })
            .unwrap_or(false),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_integral_c_style_cast_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-integral-cast");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("narrow.c");
    fs::write(
        &source_file,
        "unsigned int narrow(unsigned long value) { return (unsigned int)value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "narrow");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit integral C-style cast");
    assert!(rust.contains("pub fn narrow(value: u64) -> u32"));
    assert!(rust.contains("return (value as u32);"));
    assert_rust_snippet_compiles("typed-ir-real-clang-integral-c-style-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_fixed_width_integer_types_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-fixed-width-integers");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("fixed_width.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n\
int8_t id_i8(int8_t value) { return value; }\n\
int16_t id_i16(int16_t value) { return value; }\n\
int32_t id_i32(int32_t value) { return value; }\n\
uint16_t id_u16(uint16_t value) { return value; }\n\
int64_t id_i64(int64_t value) { return value; }\n\
uint64_t id_u64(uint64_t value) { return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);
    let cases = [
        ("id_i8", "pub fn id_i8(value: i8) -> i8"),
        ("id_i16", "pub fn id_i16(value: i16) -> i16"),
        ("id_i32", "pub fn id_i32(value: i32) -> i32"),
        ("id_u16", "pub fn id_u16(value: u16) -> u16"),
        ("id_i64", "pub fn id_i64(value: i64) -> i64"),
        ("id_u64", "pub fn id_u64(value: u64) -> u64"),
    ];

    for (function_name, expected_signature) in cases {
        let report =
            lower_function_from_clang_ast_dump_report(&environment, &source_file, function_name);

        assert_eq!(report.status, "lowered", "{:?}", report.errors);
        let function = report.function_ir.as_ref().expect("function ir");
        let [IrStmt::Return {
            value: Some(IrExpr::Var { name, .. }),
            ..
        }] = function.body.as_slice()
        else {
            panic!(
                "expected fixed-width identity return for {function_name}, got {:?}",
                function.body
            );
        };
        assert_eq!(name, "value");

        let rust = emit_rust_from_ir(function)
            .unwrap_or_else(|error| panic!("emit fixed-width integer {function_name}: {error:?}"));
        assert!(rust.contains(expected_signature), "{rust:?}");
        assert!(rust.contains("return value;"), "{rust:?}");
        assert_rust_snippet_compiles(&format!("typed-ir-real-clang-{function_name}"), &rust);
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_mutable_pointer_index_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mutable-pointer-index-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_pointer_store.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\nvoid store_at(int *out, size_t i, int value) { out[i] = value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "store_at");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, .. }] = function.body.as_slice() else {
        panic!(
            "expected mutable pointer index assignment, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Index { .. }));

    let rust = emit_rust_from_ir(function)
        .expect("emit mutable pointer index assignment from real clang AST");
    assert!(rust.contains("pub fn store_at(mut out: &mut [i32], i: usize, value: i32)"));
    assert!(rust.contains("out[i as usize] = value;"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-mutable-pointer-index-assignment",
        &rust,
    );
}

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

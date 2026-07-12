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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_mutable_record_pointer_field_read_after_if_else_return_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir =
        unique_out_dir("clang-real-mutable-record-pointer-field-read-after-if-else-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_record_pointer_field_read_after_if_else_return.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint set_then_read_point_x_if_present(struct point *p, int cond, int value) { if (cond) { p->x = value; } else { return 0; } return p->x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "set_then_read_point_x_if_present",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If { .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!(
            "expected if/return mutable record pointer read shape, got {:?}",
            function.body
        );
    };
    let emitted = emit_rust_from_ir(function)
        .expect("emit mutable record pointer field read after if/else return from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains(
            "pub fn set_then_read_point_x_if_present(mut p: &mut Point, cond: i32, value: i32) -> i32"
        ),
        "{rust}"
    );
    assert!(rust.contains("if cond != 0i32 {"), "{rust}");
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-mutable-record-pointer-field-read-after-if-return",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_mutable_record_pointer_field_read_before_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mutable-record-pointer-field-read-before-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_record_pointer_field_read_before_assignment.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint read_then_set_point_x(struct point *p, int value) { int old = p->x; p->x = value; return old; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "read_then_set_point_x",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir(function)
        .expect_err("mutable record pointer field read before assignment must fail closed");
    assert!(
        error
            .reason
            .contains("mutable record pointer field p.x is read before definite assignment"),
        "{:?}",
        error
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_mutable_record_pointer_field_compound_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mutable-record-pointer-field-compound-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_record_pointer_field_compound_assignment.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nvoid add_point_x(struct point *p, int value) { p->x += value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir(function)
        .expect("emit mutable record pointer field compound assignment from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn add_point_x(mut p: &mut Point, value: i32)"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-mutable-record-pointer-field-compound-assignment",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_mutable_record_pointer_field_compound_assignment_complex_rhs_when_enabled(
) {
    let clang_path = real_clang_ast_test_setup();
    let out_dir =
        unique_out_dir("clang-real-mutable-record-pointer-field-compound-assignment-complex-rhs");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file =
        out_dir.join("mutable_record_pointer_field_compound_assignment_complex_rhs.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nvoid add_point_x(struct point *p, int value) { p->x += value + 1; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_point_x");

    assert_eq!(report.status, "unsupported");
    assert!(
        report.errors.iter().any(|error| error
            .message
            .contains("record field compound assignment RHS")),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_struct_field_compound_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-field-compound-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_field_compound_assignment.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint add_point_x(struct point p, int value) { p.x += value; return p.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir(function)
        .expect("emit struct field compound assignment from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn add_point_x(mut p: Point, value: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-struct-field-compound-assignment", rust);
}

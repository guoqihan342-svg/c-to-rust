#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_struct_field_compound_assignment_complex_rhs_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-field-compound-assignment-complex-rhs");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_field_compound_assignment_complex_rhs.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint add_point_x(struct point p, int value) { p.x += value + 1; return p.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_point_x");

    if report.status == "lowered" {
        let function = report.function_ir.as_ref().expect("function ir");
        let error = emit_rust_from_ir(function)
            .expect_err("record field compound assignment complex RHS must fail closed");
        assert!(
            error
                .reason
                .contains("record field compound assignment RHS"),
            "{:?}",
            error
        );
    } else {
        assert!(
            report.errors.iter().any(|error| error
                .message
                .contains("record field compound assignment RHS")),
            "{:?}",
            report.errors
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_struct_local_copy_field_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-local-copy-field-read");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_local_copy_field_read.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint local_point_x(struct point p) { struct point q = p; return q.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "local_point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit struct local copy field read from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn local_point_x(p: Point) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let q: Point = p;"), "{rust}");
    assert!(rust.contains("return q.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-struct-local-copy-field-read", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_struct_local_assignment_value_copy_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-local-assignment-value-copy");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_local_assignment_value_copy.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint assign_local_point_x(struct point p, struct point r) { struct point q = p; q = r; return q.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "assign_local_point_x",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit struct local assignment copy from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn assign_local_point_x(p: Point, r: Point) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let mut q: Point = p;"), "{rust}");
    assert!(rust.contains("q = r;"), "{rust}");
    assert!(rust.contains("return q.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-struct-local-assignment-value-copy",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_struct_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-return-value");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_return_value.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nstruct point identity_point(struct point p) { return p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "identity_point");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit whole-record return from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn identity_point(p: Point) -> Point"),
        "{rust}"
    );
    assert!(rust.contains("return p;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-struct-return-value", rust);
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_struct_return_value_with_bitfield_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-return-bitfield");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_return_bitfield.c");
    fs::write(
        &source_file,
        "struct bits { unsigned int a:3; int b; };\nstruct bits identity_bits(struct bits p) { return p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "identity_bits");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir(function).expect_err("bitfield records must fail closed");
    assert!(
        error.reason.contains("record bits has no modeled fields")
            || error.reason.contains("record type bits is unsupported")
            || error.reason.contains("bitfield"),
        "{:?}",
        error
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_struct_return_value_with_volatile_field_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-return-volatile-field");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_return_volatile_field.c");
    fs::write(
        &source_file,
        "struct state { volatile int flag; int value; };\nstruct state identity_state(struct state p) { return p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "identity_state");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir(function).expect_err("volatile fields must fail closed");
    assert!(
        error.reason.contains("record state has no modeled fields")
            || error.reason.contains("record type state is unsupported")
            || error.reason.contains("volatile"),
        "{:?}",
        error
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_struct_return_value_with_packed_record_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-return-packed");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_return_packed.c");
    fs::write(
        &source_file,
        "struct __attribute__((packed)) packed_point { int x; int y; };\nstruct packed_point identity_packed(struct packed_point p) { return p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "identity_packed");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir(function).expect_err("packed records must fail closed");
    assert!(
        error
            .reason
            .contains("record packed_point has no modeled fields")
            || error.reason.contains("packed"),
        "{:?}",
        error
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_struct_return_value_with_packed_field_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-return-packed-field");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_return_packed_field.c");
    fs::write(
        &source_file,
        "struct packed_field_point { int x __attribute__((packed)); int y; };\n\
         struct packed_field_point identity_packed_field(struct packed_field_point p) { return p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "identity_packed_field",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir(function).expect_err("packed fields must fail closed");
    assert!(
        error
            .reason
            .contains("record packed_field_point has no modeled fields")
            || error
                .reason
                .contains("record type packed_field_point is unsupported")
            || error.reason.contains("packed"),
        "{:?}",
        error
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_struct_return_value_with_duplicate_tag_name_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-return-duplicate-tag");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_return_duplicate_tag.c");
    fs::write(
        &source_file,
        "int seed(void) { struct bits { int a; int b; } local; return 0; }\n\
         struct bits { unsigned int a:3; int b; };\n\
         struct bits identity_bits(struct bits p) { return p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "identity_bits");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir(function)
        .expect_err("duplicate tag names must not reuse another record inventory");
    assert!(
        error.reason.contains("record bits has no modeled fields")
            || error.reason.contains("record type bits is unsupported")
            || error.reason.contains("bitfield")
            || error.reason.contains("duplicate"),
        "{:?}",
        error
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_struct_return_value_with_self_pointer_field_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-return-self-pointer");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_return_self_pointer.c");
    fs::write(
        &source_file,
        "struct node { struct node *next; int value; };\n\
         struct node identity_node(struct node p) { return p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "identity_node");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error =
        emit_rust_from_ir(function).expect_err("self-referential pointer fields must fail closed");
    assert!(
        error.reason.contains("record node has no modeled fields")
            || error.reason.contains("record type node is unsupported")
            || error.reason.contains("pointer type"),
        "{:?}",
        error
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_readonly_record_pointer_arrow_member_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-arrow-member-read");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("arrow_member_read.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint point_x(const struct point *p) { return p->x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert!(
        matches!(
            function.body.as_slice(),
            [IrStmt::Return {
                value: Some(IrExpr::Member {
                    base,
                    field,
                    is_arrow: true,
                    ..
                }),
                ..
            }] if field == "x"
                && matches!(
                    base.as_ref(),
                    IrExpr::Var {
                        name,
                        ..
                    } if name == "p"
                )
        ),
        "{:?}",
        function.body
    );
    let emitted =
        emit_rust_from_ir(function).expect("emit readonly arrow member read from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(rust.contains("pub fn point_x(p: &Point) -> i32"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-arrow-member-read", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_null_guarded_readonly_record_pointer_arrow_member_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-null-guarded-arrow-member-read");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("null_guarded_arrow_member_read.c");
    fs::write(
        &source_file,
        "#define NULL ((void*)0)\nstruct point { int x; int y; };\nint point_x_or_zero(const struct point *p) { if (p == NULL) return 0; return p->x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "point_x_or_zero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert!(
        matches!(
            function.body.as_slice(),
            [
                IrStmt::If { .. },
                IrStmt::Return {
                    value: Some(IrExpr::Member {
                        base,
                        field,
                        is_arrow: true,
                        ..
                    }),
                    ..
                }
            ] if field == "x"
                && matches!(
                    base.as_ref(),
                    IrExpr::Var {
                        name,
                        ..
                    } if name == "p"
                )
        ),
        "{:?}",
        function.body
    );
    let emitted = emit_rust_from_ir(function)
        .expect("emit null-guarded arrow member read from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn point_x_or_zero(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("if p.is_none() {"), "{rust}");
    assert!(rust.contains("return 0i32;"), "{rust}");
    assert!(rust.contains("return p.unwrap().x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-null-guarded-arrow-member-read", rust);
}

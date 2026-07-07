#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_struct_field_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-field-read");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_field_read.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint point_x(struct point p) { return p.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir(function).expect("emit struct field read from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub fn point_x(p: Point) -> i32"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-struct-field-read", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_struct_field_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-struct-field-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("struct_field_assignment.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint set_point_x(struct point p, int value) { p.x = value; return p.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "set_point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit struct field assignment from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn set_point_x(mut p: Point, value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-struct-field-assignment", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_mutable_record_pointer_arrow_member_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mutable-arrow-member-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_arrow_member_assignment.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nvoid set_point_x(struct point *p, int value) { p->x = value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "set_point_x");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, .. }] = function.body.as_slice() else {
        panic!(
            "expected mutable arrow member assignment, got {:?}",
            function.body
        );
    };
    assert!(
        matches!(target, IrExpr::Member { field, is_arrow: true, .. } if field == "x"),
        "expected arrow member assignment target, got {target:?}"
    );

    let emitted = emit_rust_from_ir(function)
        .expect("emit mutable arrow member assignment from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn set_point_x(mut p: &mut Point, value: i32)"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-mutable-arrow-member-assignment", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typedef_record_pointer_opaque_field_write_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typedef-record-pointer-opaque-field-write");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("typedef_record_pointer_opaque_field_write.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\n\
typedef struct fdb_blob { void *buf; size_t size; } *fdb_blob_t;\n\
fdb_blob_t make_blob_typedef(fdb_blob_t blob, const void *value, size_t len) {\n\
    blob->buf = (void *)value;\n\
    blob->size = len;\n\
    return blob;\n\
}\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "make_blob_typedef");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        target: buf_target,
        value: buf_value,
        ..
    }, IrStmt::Assign {
        target: size_target,
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected typedef record pointer field writes and identity return, got {:?}",
            function.body
        );
    };
    assert!(
        matches!(buf_target, IrExpr::Member { field, is_arrow: true, .. } if field == "buf"),
        "expected blob->buf assignment target, got {buf_target:?}"
    );
    assert!(
        matches!(size_target, IrExpr::Member { field, is_arrow: true, .. } if field == "size"),
        "expected blob->size assignment target, got {size_target:?}"
    );
    match buf_value {
        IrExpr::Cast {
            target,
            expr,
            implicit: false,
            ..
        } => {
            assert_eq!(target.canonical, "void *");
            assert!(matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "value"));
        }
        other => panic!("expected explicit opaque pointer cast RHS, got {other:?}"),
    }
    assert_eq!(return_name, "blob");

    let emitted = emit_rust_from_ir(function)
        .expect("emit typedef-backed record pointer field writes from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("pub buf: *mut core::ffi::c_void"), "{rust}");
    assert!(rust.contains("pub size: usize"), "{rust}");
    assert!(
        rust.contains(
            "pub fn make_blob_typedef(mut blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> &mut FdbBlob"
        ),
        "{rust}"
    );
    assert!(
        rust.contains("blob.buf = (value as *mut core::ffi::c_void);"),
        "{rust}"
    );
    assert!(rust.contains("blob.size = len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-typedef-record-pointer-opaque-field-write",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_mutable_record_pointer_field_read_after_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mutable-record-pointer-field-read-after-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mutable_record_pointer_field_read_after_assignment.c");
    fs::write(
        &source_file,
        "struct point { int x; int y; };\nint set_then_read_point_x(struct point *p, int value) { p->x = value; return p->x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "set_then_read_point_x",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir(function)
        .expect("emit mutable record pointer field read after assignment from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(rust.contains("pub y: i32"), "{rust}");
    assert!(
        rust.contains("pub fn set_then_read_point_x(mut p: &mut Point, value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-mutable-record-pointer-field-read-after-assignment",
        rust,
    );
}

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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_initialized_decl_stmt_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-initialized-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_init.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_init(uint32_t crc) { uint32_t next = crc; return next; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_init");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name,
        init: Some(IrExpr::Var {
            name: init_name, ..
        }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected initialized decl followed by return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "next");
    assert_eq!(init_name, "crc");

    let rust = emit_rust_from_ir(function).expect("emit initialized decl from real clang AST");
    assert!(rust.contains("pub fn crc_init(crc: u32) -> u32"));
    assert!(rust.contains("let mut next: u32 = crc;"));
    assert!(rust.contains("return next;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-initialized-decl", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_uninitialized_local_decl_assigned_before_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-uninitialized-local-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("assign_after_decl.c");
    fs::write(
        &source_file,
        "int assign_after_decl(void) { int tmp; tmp = 7; return tmp; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "assign_after_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name, init: None, ..
    }, IrStmt::Assign {
        target,
        value: IrExpr::LitInt { value, .. },
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected uninitialized decl, assignment, and return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "tmp");
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "tmp"));
    assert_eq!(*value, 7);
    assert_eq!(return_name, "tmp");

    let emitted =
        emit_rust_from_ir(function).expect("emit assigned uninitialized local from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn assign_after_decl() -> i32"), "{rust}");
    assert!(rust.contains("let mut tmp: i32;"), "{rust}");
    assert!(rust.contains("tmp = 7i32;"), "{rust}");
    assert!(rust.contains("return tmp;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-uninitialized-local-decl", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_local_fixed_array_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-local-array-init");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("lookup_local_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t lookup_local_table(size_t i) { uint32_t table[3] = {1U, 2U, 3U}; return table[i]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "lookup_local_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name,
        init: Some(IrExpr::ArrayLiteral { elements, .. }),
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Index { base, index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected local array declaration followed by index return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "table");
    assert_eq!(elements.len(), 3);
    assert!(matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "table"));
    assert!(matches!(index.as_ref(), IrExpr::Var { name, .. } if name == "i"));

    let rust = emit_rust_from_ir(function).expect("emit local array init from real clang AST");
    assert!(rust.contains("pub fn lookup_local_table(i: usize) -> u32"));
    assert!(rust.contains("let table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-local-array-init", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_local_fixed_array_index_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-local-array-index-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("replace_local_table_slot.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t replace_local_table_slot(size_t i, uint32_t value) { uint32_t table[3] = {1U, 2U, 3U}; table[i] = value; return table[i]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "replace_local_table_slot",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, .. }, IrStmt::Assign { target, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected local array declaration, index assignment, and return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "table");
    assert!(matches!(target, IrExpr::Index { .. }));

    let rust = emit_rust_from_ir(function).expect("emit local array index assignment");
    assert!(rust.contains("pub fn replace_local_table_slot(i: usize, value: u32) -> u32"));
    assert!(rust.contains("let mut table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("table[i as usize] = value;"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-local-array-index-assignment", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_local_array_initializer_call_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-local-array-call-init-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("lookup_local_table_call_init.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t helper(void);\nuint32_t lookup_local_table_call_init(size_t i) { uint32_t table[3] = {helper(), 2U, 3U}; return table[i]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "lookup_local_table_call_init",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    let message = report
        .errors
        .first()
        .map(|error| error.message.as_str())
        .unwrap_or("");
    assert!(message.contains("InitListExpr"), "{message}");
    assert!(message.contains("initializer element 0"), "{message}");
    assert!(
        message.contains("only pure integer literal elements"),
        "{message}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_initialized_decl_with_direct_call_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-initialized-decl-call-lower");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("init_call.c");
    fs::write(
        &source_file,
        "int helper(void);\nint init_call(void) { int value = helper(); return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "init_call");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name,
        init: Some(IrExpr::Call { callee, args, .. }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected direct call initializer followed by return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "value");
    assert_eq!(callee, "helper");
    assert!(args.is_empty());

    let emitted =
        emit_rust_from_ir(function).expect("emit initialized direct call from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn init_call() -> i32"));
    assert!(rust.contains("let mut value: i32 = helper();"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-initialized-direct-call",
        &format!("fn helper() -> i32 {{ 0 }}\n{rust}"),
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_strlen_model_with_target_abi_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let source_root = unique_out_dir("clang-real-strlen-target-abi-lower");
    let source_dir = source_root.join("src");
    fs::create_dir_all(&source_dir).unwrap();
    let source_file = source_dir.join("name_len.c");
    fs::write(
        &source_file,
        "typedef unsigned long size_t;\nsize_t strlen(const char *);\nsize_t name_len(const char *name) { return strlen(name); }\n",
    )
    .unwrap();
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "strlen-target-abi",
        "source_commit": "source-sha",
        "function_name": "name_len",
        "c_source": "size_t name_len(const char *name) { return strlen(name); }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root.to_string_lossy().replace('\\', "/"),
        "source_file": "src/name_len.c",
        "source_file_hashes": {
            "src/name_len.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/name_len.c",
            "line_start": 3,
            "line_end": 3,
            "byte_start": 63,
            "byte_end": 119,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "char_width": 8,
                "plain_char_signed": true,
                "short_width": 16,
                "long_width": 64,
                "long_long_width": 64,
                "pointer_width": 64
            },
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "x86_64-unknown-linux-gnu",
            "compiler_command_source": "unit-test",
            "clang_available": true
        }
    }))
    .unwrap();
    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_parse_spec_report(&environment, &parse_spec);

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Call {
            callee, args, ty, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected strlen return call, got {:?}", function.body);
    };
    assert_eq!(callee, "strlen");
    assert_eq!(args.len(), 1);
    assert_eq!(ty.spelled, "size_t");

    let emitted = emit_rust_from_ir(function).expect("emit strlen model from real clang AST");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn name_len(name: &[i8]) -> usize"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return name.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\");"
        ),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-strlen-model", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_nested_direct_call_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-direct-call-lower");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("nested_direct_call.c");
    fs::write(
        &source_file,
        "int inner(int value) { return value + 1; }\nint outer(int value) { return value; }\nint nested_direct_call(int value) { return outer(inner(value)); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "nested_direct_call");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Call { callee, args, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected nested direct call return, got {:?}",
            function.body
        );
    };
    assert_eq!(callee, "outer");
    let [IrExpr::Call {
        callee: inner_callee,
        args: inner_args,
        ..
    }] = args.as_slice()
    else {
        panic!("expected one nested direct call arg, got {args:?}");
    };
    assert_eq!(inner_callee, "inner");
    assert_eq!(inner_args.len(), 1);

    let emitted = emit_rust_from_ir(function).expect("emit nested direct call from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn nested_direct_call(value: i32) -> i32"));
    assert!(rust.contains("return outer(inner(value));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-direct-call",
        &format!(
            "fn inner(value: i32) -> i32 {{ value + 1 }}\nfn outer(value: i32) -> i32 {{ value }}\n{rust}"
        ),
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_multiple_nested_direct_call_args_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-multiple-nested-direct-call-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("multiple_nested_direct_call.c");
    fs::write(
        &source_file,
        "int left(int value) { return value + 1; }\nint right(int value) { return value + 2; }\nint outer2(int a, int b) { return a + b; }\nint multiple_nested_direct_call(int value) { return outer2(left(value), right(value)); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "multiple_nested_direct_call",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    let message = report
        .errors
        .first()
        .map(|error| error.message.as_str())
        .unwrap_or("");
    assert!(
        message.contains("multiple nested call arguments are outside the bounded call subset"),
        "{message}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_multi_var_decl_stmt_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-multi-var-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("multi_decl.c");
    fs::write(
        &source_file,
        "int multi_decl(void) { int a = 1, b = 2; return a + b; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "multi_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name: a_name,
        init: Some(IrExpr::LitInt { value: a_value, .. }),
        ..
    }, IrStmt::Decl {
        name: b_name,
        init: Some(IrExpr::LitInt { value: b_value, .. }),
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Binary { .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected two declarations followed by return, got {:?}",
            function.body
        );
    };
    assert_eq!(a_name, "a");
    assert_eq!(*a_value, 1);
    assert_eq!(b_name, "b");
    assert_eq!(*b_value, 2);

    let emitted = emit_rust_from_ir(function)
        .unwrap_or_else(|error| panic!("emit multi var decl: {error:?}"));
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn multi_decl() -> i32"), "{rust}");
    assert!(rust.contains("let mut a: i32 = 1i32;"), "{rust}");
    assert!(rust.contains("let mut b: i32 = 2i32;"), "{rust}");
    assert!(
        rust.contains("return a.checked_add(b).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-multi-var-decl", rust);
}

#[test]
fn pointer_field_writes_record_lvalue_and_boundary_decisions() {
    let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr-fields".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; addr->sin_port = port; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ip4-addr-fields");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.slice_id, "ip4-addr-fields");
    let plan = json_file(out_dir.join("l3-ip4-addr-fields-auto-translation-plan.json"));
    assert_eq!(
        plan["translation_source"]["selected"],
        "legacy-string-translator"
    );
    let plan_errors = plan["errors"].as_array().expect("plan errors");
    assert!(
        plan_errors.iter().all(|error| {
            let kind = error["kind"].as_str().unwrap_or_default();
            kind.starts_with("legacy_") && kind.ends_with("_retired")
        }),
        "expected only retired-legacy diagnostics, got {plan_errors:?}"
    );

    let pointer_graph = json_file(out_dir.join("l3-ip4-addr-fields-pointer-graph.json"));
    assert_eq!(pointer_graph["status"], "recorded");
    let addr = pointer_graph["pointer_graph"]["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|node| node["id"] == "addr")
        .expect("addr pointer node");
    let write_effects = addr["write_effects"]
        .as_array()
        .expect("addr write effects");
    assert!(write_effects
        .iter()
        .any(|effect| effect == "addr->sin_family"));
    assert!(write_effects
        .iter()
        .any(|effect| effect == "addr->sin_port"));

    let cfg = json_file(out_dir.join("l3-ip4-addr-fields-cfg.json"));
    let lvalue_kinds = cfg["cfg"]["functions"][0]["blocks"][0]["lvalue_kinds"]
        .as_array()
        .expect("lvalue kinds");
    let addr_decisions = addr["boundary_decisions"]
        .as_array()
        .expect("addr boundary decisions");

    assert!(lvalue_kinds.iter().any(|kind| kind == "pointer_field"));
    assert!(addr_decisions
        .iter()
        .any(|decision| decision == "safe_wrapper_candidate"));
    assert!(plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .iter()
        .any(|rule| rule == "pointer-field-write"));
}

#[test]
fn unproven_input_buffer_read_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-buffer-read".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_buffer_read".to_string(),
        c_source: "int bad_buffer_read(const int* values, int i, int* out) { out[0] = values[i]; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-buffer-read");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-bad-buffer-read-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-buffer-read-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-bad-buffer-read-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unproven_pointer_arithmetic_read_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-read".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_read".to_string(),
        c_source: "int bad_ptr_arith_read(const int* values, int i, int* out) { out[0] = *(values + i); return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-ptr-arith-read");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-read-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-ptr-arith-read-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-read-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unproven_pointer_arithmetic_output_write_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_out".to_string(),
        c_source:
            "int bad_ptr_arith_out(int* out, int i, int value) { *(out + i) = value; return 0; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-ptr-arith-out");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-out-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-ptr-arith-out-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-out-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn complex_pointer_arithmetic_output_write_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-complex-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_complex_out".to_string(),
        c_source: "int bad_ptr_arith_complex_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i + 1) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("bad-ptr-arith-complex-out");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-bad-ptr-arith-complex-out-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-bad-ptr-arith-complex-out-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_lvalue"),
        "{:?}",
        plan["errors"]
    );
    let events = fs::read_to_string(
        out_dir.join("l3-bad-ptr-arith-complex-out-auto-translation-events.jsonl"),
    )
    .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unsupported_complex_lvalues_block_without_false_success() {
    for (slice_id, function_name, c_source) in [
        (
            "unbounded-index",
            "unbounded_index",
            "int unbounded_index(int* out, int i, int value) { out[i] = value; return 0; }",
        ),
        (
            "field-assignment",
            "field_assignment",
            "int field_assignment(int value) { state.field = value; return value; }",
        ),
        (
            "pointer-arithmetic-complex",
            "pointer_arithmetic_complex",
            "int pointer_arithmetic_complex(int* out, int i, int value) { *(out + i + 1) = value; return 0; }",
        ),
    ] {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: slice_id.to_string(),
            source_commit: "1234567".to_string(),
            function_name: function_name.to_string(),
            c_source: c_source.to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir(slice_id);

        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

        assert_eq!(manifest.status, "blocked", "{slice_id}");
        let rust_draft =
            fs::read_to_string(out_dir.join(format!("l3-{slice_id}-rust-draft.rs"))).unwrap();
        assert!(rust_draft.is_empty(), "{slice_id}: {rust_draft}");
        let plan = json_file(out_dir.join(format!("l3-{slice_id}-auto-translation-plan.json")));
        assert_eq!(plan["status"], "blocked", "{slice_id}");
        assert!(
            plan["errors"]
                .as_array()
                .expect("plan errors")
                .iter()
                .any(|error| error["kind"] == "unsupported_lvalue"),
            "{slice_id}: {:?}",
            plan["errors"]
        );
        let events = fs::read_to_string(
            out_dir.join(format!("l3-{slice_id}-auto-translation-events.jsonl")),
        )
        .unwrap();
        assert!(
            !events.contains("\"event\":\"translation_generated\""),
            "{slice_id}"
        );
    }
}

#[test]
fn blocks_pointer_out_param_without_observable_write() {
    let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr-no-write".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source:
            "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { return 0; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ip4-addr-no-write");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-ip4-addr-no-write-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-ip4-addr-no-write-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_pointer_pattern"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-ip4-addr-no-write-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn blocks_unsupported_local_declaration_type_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "unknown-local".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "unknown_local".to_string(),
        c_source: "int unknown_local(int value) { alias_t local = value; return value; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("unknown-local");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-unknown-local-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-unknown-local-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-unknown-local-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn blocks_unsupported_call_expressions_without_rust_draft() {
    for (slice_id, c_source) in [
        (
            "nested-call-expression",
            "int nested_call_expression(int value) { return helper(other(value)); }",
        ),
        (
            "function-pointer-call-expression",
            "int function_pointer_call_expression(int value) { return (*fp)(value); }",
        ),
        (
            "side-effect-call-argument",
            "int side_effect_call_argument(int value) { return helper(value++); }",
        ),
        (
            "assert-call-expression",
            "int assert_call_expression(int value) { assert(value); return value; }",
        ),
    ] {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: slice_id.to_string(),
            source_commit: "1234567".to_string(),
            function_name: slice_id.replace('-', "_"),
            c_source: c_source.to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir(slice_id);

        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

        assert_eq!(manifest.status, "blocked", "{slice_id}");
        let rust_draft =
            fs::read_to_string(out_dir.join(format!("l3-{slice_id}-rust-draft.rs"))).unwrap();
        assert!(rust_draft.is_empty(), "{slice_id}: {rust_draft}");
        let plan = json_file(out_dir.join(format!("l3-{slice_id}-auto-translation-plan.json")));
        assert_eq!(plan["status"], "blocked", "{slice_id}");
        assert!(
            plan["errors"]
                .as_array()
                .expect("plan errors")
                .iter()
                .any(|error| error["kind"] == "unsupported_syntax"),
            "{slice_id}: {:?}",
            plan["errors"]
        );
        let events = fs::read_to_string(
            out_dir.join(format!("l3-{slice_id}-auto-translation-events.jsonl")),
        )
        .unwrap();
        assert!(
            !events.contains("\"event\":\"translation_generated\""),
            "{slice_id}"
        );
    }
}

#[test]
fn blocks_increment_expression_value_without_rust_draft() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "inc-expression".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "inc_expression".to_string(),
        c_source: "int inc_expression(int value) { return value++; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("inc-expression");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-inc-expression-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-inc-expression-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-inc-expression-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn blocks_unknown_or_unsupported_statement_without_rust_draft() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "unsupported-stmt".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "unsupported_stmt".to_string(),
        c_source: "int unsupported_stmt(int value) { value ? value : 0; return value; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("unsupported-stmt");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-unsupported-stmt-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-unsupported-stmt-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_syntax"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-unsupported-stmt-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unsupported_goto_blocks_translation_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "goto-case".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "again".to_string(),
        c_source: "int again(int x) { again: x++; if (x < 10) goto again; return x; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("goto-case");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-goto-case-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-goto-case-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_control_flow"),
        "{:?}",
        plan["errors"]
    );
    let cfg = json_file(out_dir.join("l3-goto-case-cfg.json"));
    let unsupported = cfg["cfg"]["functions"][0]["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(
        unsupported.iter().any(|node| node == "goto"),
        "{unsupported:?}"
    );
    let events =
        fs::read_to_string(out_dir.join("l3-goto-case-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unsupported_goto_records_minimal_cfg_blocks_and_edges() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "goto-cfg-evidence".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "again".to_string(),
        c_source: "int again(int x) { again: x++; if (x < 10) goto again; return x; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let out_dir = unique_out_dir("goto-cfg-evidence");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-goto-cfg-evidence-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let cfg = json_file(out_dir.join("l3-goto-cfg-evidence-cfg.json"));
    let function = &cfg["cfg"]["functions"][0];
    let unsupported = function["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(unsupported.iter().any(|node| node == "label:again"));
    assert!(unsupported.iter().any(|node| node == "goto:again"));
    assert!(unsupported
        .iter()
        .any(|node| node == "relooper_refusal:goto"));
    let structured = &function["structured_control_flow"];
    assert!(
        structured.is_object(),
        "goto refusal should carry structured recovery evidence: {structured:?}"
    );
    assert_eq!(structured["has_goto"], true);
    assert_eq!(structured["has_switch"], false);
    assert_eq!(structured["relooper_required"], true);
    assert!(structured["relooper_preconditions"]
        .as_array()
        .expect("relooper preconditions")
        .iter()
        .any(|item| item == "goto_target_resolved"));
    assert!(structured["relooper_refusals"]
        .as_array()
        .expect("relooper refusals")
        .iter()
        .any(|item| item == "goto_requires_structured_recovery"));
    assert!(structured["scope_note"]
        .as_str()
        .expect("scope note")
        .contains("no Rust candidate lowering"));
    let blocks = function["blocks"].as_array().expect("cfg blocks");
    assert!(blocks.iter().any(|block| block["id"] == "label-again"));
    assert!(blocks.iter().any(|block| block["id"] == "goto-again"));
    let edges: Vec<&Value> = blocks
        .iter()
        .flat_map(|block| block["edges"].as_array().expect("block edges").iter())
        .collect();
    assert!(edges.iter().any(|edge| **edge == "entry->goto-again"));
    assert!(edges.iter().any(|edge| **edge == "goto-again->label-again"));
    assert!(!edges.iter().any(|edge| **edge == "entry->goto"));
    let events =
        fs::read_to_string(out_dir.join("l3-goto-cfg-evidence-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unsupported_switch_blocks_translation_until_cfg_relooper_exists() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "switch-case".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "choose".to_string(),
        c_source: "int choose(int x) { switch (x) { case 1: return 1; default: return 0; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("switch-case");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-switch-case-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let plan = json_file(out_dir.join("l3-switch-case-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "unsupported_control_flow"),
        "{:?}",
        plan["errors"]
    );
    let cfg = json_file(out_dir.join("l3-switch-case-cfg.json"));
    let unsupported = cfg["cfg"]["functions"][0]["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(
        unsupported.iter().any(|node| node == "switch"),
        "{unsupported:?}"
    );
    let events =
        fs::read_to_string(out_dir.join("l3-switch-case-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn unsupported_switch_records_case_default_cfg_edges() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "switch-cfg-evidence".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "choose".to_string(),
        c_source: "int choose(int x) { switch (x) { case 1: return 1; default: return 0; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let out_dir = unique_out_dir("switch-cfg-evidence");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft =
        fs::read_to_string(out_dir.join("l3-switch-cfg-evidence-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let cfg = json_file(out_dir.join("l3-switch-cfg-evidence-cfg.json"));
    let function = &cfg["cfg"]["functions"][0];
    let unsupported = function["unsupported_control_flow"]
        .as_array()
        .expect("unsupported control flow nodes");
    assert!(unsupported.iter().any(|node| node == "case:1"));
    assert!(unsupported.iter().any(|node| node == "default"));
    assert!(unsupported
        .iter()
        .any(|node| node == "relooper_refusal:switch"));
    let structured = &function["structured_control_flow"];
    assert!(
        structured.is_object(),
        "switch refusal should carry structured recovery evidence: {structured:?}"
    );
    assert_eq!(structured["has_goto"], false);
    assert_eq!(structured["has_switch"], true);
    assert_eq!(structured["relooper_required"], true);
    assert!(structured["relooper_preconditions"]
        .as_array()
        .expect("relooper preconditions")
        .iter()
        .any(|item| item == "switch_cases_enumerated"));
    assert!(structured["relooper_refusals"]
        .as_array()
        .expect("relooper refusals")
        .iter()
        .any(|item| item == "switch_requires_structured_recovery"));
    assert!(structured["scope_note"]
        .as_str()
        .expect("scope note")
        .contains("no Rust candidate lowering"));
    let blocks = function["blocks"].as_array().expect("cfg blocks");
    assert!(blocks.iter().any(|block| block["id"] == "switch-0"));
    assert!(blocks.iter().any(|block| block["id"] == "case-1"));
    assert!(blocks.iter().any(|block| block["id"] == "default"));
    let edges: Vec<&Value> = blocks
        .iter()
        .flat_map(|block| block["edges"].as_array().expect("block edges").iter())
        .collect();
    assert!(edges.iter().any(|edge| **edge == "entry->switch-0"));
    assert!(edges.iter().any(|edge| **edge == "switch-0->case-1"));
    assert!(edges.iter().any(|edge| **edge == "switch-0->default"));
    assert!(!edges.iter().any(|edge| **edge == "entry->switch"));
    let events =
        fs::read_to_string(out_dir.join("l3-switch-cfg-evidence-auto-translation-events.jsonl"))
            .unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn missing_clang_profile_records_type_uncertainty() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "ambiguous".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "uses_alias".to_string(),
        c_source: "alias_t uses_alias(alias_t value) { return value; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ambiguous");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.status, "blocked");
    let rust_draft = fs::read_to_string(out_dir.join("l3-ambiguous-rust-draft.rs")).unwrap();
    assert!(rust_draft.is_empty(), "{rust_draft}");
    let type_map = json_file(out_dir.join("l3-ambiguous-type-map.json"));
    assert_eq!(type_map["status"], "uncertain");
    assert!(
        type_map["type_map"]["uncertainties"]
            .as_array()
            .expect("type map uncertainties")
            .iter()
            .any(|item| item["reason"]
                .as_str()
                .expect("uncertainty reason")
                .contains("clang-backed type extraction")),
        "{:?}",
        type_map["type_map"]["uncertainties"]
    );
    let plan = json_file(out_dir.join("l3-ambiguous-auto-translation-plan.json"));
    assert_eq!(plan["status"], "blocked");
    assert!(
        plan["errors"]
            .as_array()
            .expect("plan errors")
            .iter()
            .any(|error| error["kind"] == "type_uncertainty"),
        "{:?}",
        plan["errors"]
    );
    let events =
        fs::read_to_string(out_dir.join("l3-ambiguous-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[test]
fn writes_translation_artifacts_for_l3_manifest_binding() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "add-one".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "add_one".to_string(),
        c_source: "int add_one(int value) { return value + 1; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("add-one");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.target_id, "demo");
    assert_eq!(manifest.slice_id, "add-one");
    for path in [
        "l3-add-one-auto-translation-plan.json",
        "l3-add-one-auto-translation-events.jsonl",
        "l3-add-one-type-map.json",
        "l3-add-one-cfg.json",
        "l3-add-one-pointer-graph.json",
        "l3-add-one-ai-candidate-manifest.json",
        "l3-add-one-blocked-repairs.json",
        "l3-add-one-rust-draft.rs",
    ] {
        assert!(out_dir.join(path).exists(), "{path}");
    }
    let plan = fs::read_to_string(out_dir.join("l3-add-one-auto-translation-plan.json")).unwrap();
    assert!(plan.contains("\"status\": \"blocked\""));
    assert!(plan.contains("\"kind\": \"legacy_"));
    assert!(plan.contains("_retired\""));
    let events =
        fs::read_to_string(out_dir.join("l3-add-one-auto-translation-events.jsonl")).unwrap();
    assert!(!events.contains("\"event\":\"translation_generated\""));
}

#[cfg(not(feature = "clang-frontend"))]
#[test]
fn default_translation_artifacts_do_not_emit_clang_dry_run() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("no-clang-dry-run");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-dry-run.json")
        .exists());
    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-lowering-report.json")
        .exists());
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-lowering-report.json")));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_frontend_feature_writes_dry_run_artifact_from_real_tu_metadata() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc", "tests"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("clang-dry-run");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let dry_run = json_file(out_dir.join("l3-real-fdb-calc-crc32-clang-dry-run.json"));

    assert!(manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
    assert_eq!(dry_run["schema_version"], 1);
    assert_eq!(dry_run["artifact_kind"], "clang-dry-run");
    assert_eq!(dry_run["status"], "diagnostic_only");
    assert_eq!(dry_run["frontend"], "clang");
    assert_eq!(dry_run["claim_boundary"]["role"], "diagnostic_only");
    assert_eq!(dry_run["active_frontend"]["kind"], "clang_ast_dump_json");
    assert_eq!(dry_run["active_frontend"]["uses_libclang"], false);
    assert_eq!(dry_run["dry_run"]["status"], "diagnostic_only");
    assert_eq!(dry_run["dry_run"]["source_file"], "src/fdb_utils.c");
    assert_eq!(
        dry_run["dry_run"]["arguments"],
        serde_json::json!([
            "-IC:/src/FlashDB/inc",
            "-IC:/src/FlashDB/tests",
            "-DFDB_USING_FILE_POSIX_MODE"
        ])
    );
    assert_eq!(
        dry_run["metadata"]["source_file_hashes"]["src/fdb_utils.c"],
        "source-file-sha"
    );
    assert!(dry_run["errors"].as_array().unwrap().is_empty());
}

#[cfg(all(feature = "clang-frontend", not(feature = "clang-lowering-report")))]
#[test]
fn clang_frontend_feature_does_not_emit_lowering_report_without_opt_in() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/demo",
        "source_file": "add_one.c",
        "source_file_hashes": {
            "add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "add_one.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 43,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("no-clang-lowering-report");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(!out_dir
        .join("l3-add-one-clang-lowering-report.json")
        .exists());
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-add-one-clang-lowering-report.json")));
}

#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_feature_blocks_retired_legacy_fallback_when_unavailable() {
    let source_root = unique_out_dir("clang-lowering-source");
    fs::create_dir_all(&source_root).unwrap();
    fs::write(
        source_root.join("add_one.c"),
        "int add_one(int value) { return value + 1; }\n",
    )
    .unwrap();
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root,
        "source_file": "add_one.c",
        "source_file_hashes": {
            "add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "add_one.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 43,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("clang-lowering-report");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let report = json_file(out_dir.join("l3-add-one-clang-lowering-report.json"));

    if report["typed_ir_candidate"]["status"] == "generated" {
        assert_eq!(manifest.status, "generated");
    } else {
        assert_eq!(manifest.status, "blocked");
        let plan = json_file(out_dir.join("l3-add-one-auto-translation-plan.json"));
        assert_eq!(plan["errors"][0]["kind"], "legacy_fallback_retired");
        let events =
            fs::read_to_string(out_dir.join("l3-add-one-auto-translation-events.jsonl")).unwrap();
        assert!(events.contains("\"event\":\"translation_fallback\""));
        assert!(!events.contains("\"event\":\"translation_generated\""));
    }
    assert!(manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-add-one-clang-lowering-report.json")));
    assert_eq!(report["schema_version"], 1);
    assert_eq!(report["artifact_kind"], "clang-lowering-report");
    assert_eq!(report["frontend"], "clang");
    assert_eq!(report["function_name"], "add_one");
    assert_eq!(report["claim_boundary"]["role"], "diagnostic_only");
    assert_eq!(report["claim_boundary"]["affects_manifest_status"], false);
    assert_eq!(report["claim_boundary"]["affects_semantic_pass"], false);
    assert_eq!(report["claim_boundary"]["authoritative_evidence"], false);
    assert!(["lowered", "unavailable", "blocked", "unsupported"]
        .contains(&report["status"].as_str().unwrap()));
    assert_eq!(report["lowering_report"]["function_name"], "add_one");
    assert_eq!(
        report["lowering_report"]["source_file"],
        report["source_file"]
    );
    assert!(report["typed_ir_candidate"].is_object());
    assert_eq!(report["typed_ir_candidate"]["semantic_pass"], false);
    assert!(report["typed_ir_candidate"]["readonly_globals"]
        .as_array()
        .is_some());
    if report["typed_ir_candidate"]["status"] == "generated" {
        assert_eq!(
            report["typed_ir_candidate"]["candidate_route"]["route"],
            "GenericTypedIr"
        );
        assert_eq!(
            report["typed_ir_candidate"]["candidate_route"]["candidate_generator"],
            "GenericTypedIrEmitter"
        );
    }
    assert_eq!(
        report["metadata"]["logical_source_file"],
        serde_json::json!("add_one.c")
    );
    assert!(report["diagnostics"].as_array().is_some());
    assert!(report["errors"].as_array().is_some());
    assert!(out_dir.join("l3-add-one-rust-draft.rs").exists());
}

#[cfg(feature = "clang-lowering-report")]
fn write_one_shot_fake_clang(out_dir: &std::path::Path) -> (PathBuf, PathBuf) {
    let fake_clang = out_dir.join(if cfg!(windows) {
        "fake-clang.cmd"
    } else {
        "fake-clang"
    });
    let count_file = out_dir.join("fake-clang-count.txt");
    let ast_file = out_dir.join("add_one_ast.json");
    fs::write(
        &ast_file,
        include_str!("../../fixtures/clang_ast/add_one_ast.json"),
    )
    .unwrap();

    if cfg!(windows) {
        fs::write(
            &fake_clang,
            format!(
                "@echo off\r\n\
if not exist \"{count}\" (\r\n\
  >\"{count}\" echo 1\r\n\
  type \"{ast}\"\r\n\
  exit /b 0\r\n\
)\r\n\
set /p CURRENT=<\"{count}\"\r\n\
set /a NEXT=%CURRENT%+1\r\n\
>\"{count}\" echo %NEXT%\r\n\
echo fake clang invoked more than once 1>&2\r\n\
exit /b 1\r\n",
                count = count_file.display(),
                ast = ast_file.display()
            ),
        )
        .unwrap();
    } else {
        fs::write(
            &fake_clang,
            format!(
                "#!/bin/sh\n\
if [ ! -f '{count}' ]; then\n\
  echo 1 > '{count}'\n\
  cat '{ast}'\n\
  exit 0\n\
fi\n\
current=$(cat '{count}')\n\
echo $((current + 1)) > '{count}'\n\
echo 'fake clang invoked more than once' >&2\n\
exit 1\n",
                count = count_file.display(),
                ast = ast_file.display()
            ),
        )
        .unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&fake_clang, fs::Permissions::from_mode(0o755)).unwrap();
        }
    }

    (fake_clang, count_file)
}

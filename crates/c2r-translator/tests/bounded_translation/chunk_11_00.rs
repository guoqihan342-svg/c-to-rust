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
    assert_rust_snippet_compiles("typed-ir-real-clang-struct-field-read", rust);
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
    assert_rust_snippet_compiles("typed-ir-real-clang-struct-field-assignment", rust);
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
fn clang_ast_dump_emits_readonly_record_pointer_raw_pointer_field_return_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-readonly-record-pointer-raw-field-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("readonly_record_pointer_raw_field_return.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\n#include <stdint.h>\n\
struct fdb_blob { uint8_t *buf; size_t size; };\n\
uint8_t *blob_buf(const struct fdb_blob *blob) { return blob->buf; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "blob_buf");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Member {
                field,
                is_arrow: true,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected raw pointer field return from readonly record pointer, got {:?}",
            function.body
        );
    };
    assert_eq!(field, "buf");

    let emitted = emit_rust_from_ir(function)
        .expect("emit raw pointer field return from real clang AST");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("pub buf: *mut u8"), "{rust}");
    assert!(
        rust.contains("pub fn blob_buf(blob: &FdbBlob) -> *mut u8"),
        "{rust}"
    );
    assert!(rust.contains("return blob.buf;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-readonly-record-pointer-raw-field-return",
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

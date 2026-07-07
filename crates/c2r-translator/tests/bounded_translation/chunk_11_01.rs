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

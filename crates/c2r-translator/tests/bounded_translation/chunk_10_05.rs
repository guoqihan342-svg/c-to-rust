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

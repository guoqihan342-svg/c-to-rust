#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_crc_update_expr_with_postinc_and_shift_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-crc-update-postinc-shift");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_update_expr.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_update_expr(uint32_t crc, const uint8_t *p) { return table[(crc ^ *p++) & 0xff] ^ (crc >> 8); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_update_expr");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::BitXor,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected crc update return, got {:?}", function.body);
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Index { .. }));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Shr,
            ..
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_const_pointer_table_index_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-pointer-table-index-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t read_table(const uint32_t *table, uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit const pointer table index");
    assert!(rust.contains("pub fn read_table(table: &[u32], idx: u32) -> u32"));
    assert!(rust.contains("return table[idx as usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-const-pointer-table-index", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_const_void_byte_cursor_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-void-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_from_void.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_from_void(const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return *p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "read_byte_from_void",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit const void byte cursor read");
    assert!(rust.contains("pub fn read_byte_from_void(buf: &[u8]) -> u8"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return byte0;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-const-void-byte-cursor-read", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_nested_const_void_byte_cursor_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-const-void-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_byte.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_byte(uint32_t crc, const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return crc ^ (uint32_t)*p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_byte");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit nested const void byte cursor read");
    assert!(rust.contains("pub fn crc_xor_byte(crc: u32, buf: &[u8]) -> u32"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-const-void-byte-cursor-read",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_nested_const_u8_byte_cursor_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-const-u8-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_byte_from_u8.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_byte_from_u8(uint32_t crc, const uint8_t *p) { return crc ^ (uint32_t)*p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "crc_xor_byte_from_u8",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit nested const u8 byte cursor read");
    assert!(rust.contains("pub fn crc_xor_byte_from_u8(crc: u32, p: &[u8]) -> u32"));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-const-u8-byte-cursor-read",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_crc_update_assignment_with_pointer_table_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-crc-update-assignment-pointer-table-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("update_crc_step_from_clang.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t update_crc_step_from_clang(uint32_t crc, const uint8_t *p, const uint32_t *table) { crc = table[(crc ^ (uint32_t)*p++) & 0xffU] ^ (crc >> 8U); return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "update_crc_step_from_clang",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit clang crc update assignment with pointer table");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains(
        "pub fn update_crc_step_from_clang(mut crc: u32, p: &[u8], table: &[u32]) -> u32"
    ));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(rust.contains("crc = (table[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ crc.checked_shr(core::convert::TryFrom::try_from(8u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\"));"));
    assert!(rust.contains("return crc;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-crc-update-assignment-pointer-table",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_flashdb_crc32_from_lowered_ir_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-flashdb-crc32-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("fdb_utils.c");
    let table_values = repeated_c_u32_initializer(256, "0U");
    fs::write(
        &source_file,
        format!(
            "#include <stdint.h>\n#include <stddef.h>\nstatic const uint32_t crc32_table[256] = {{ {table_values} }};\nuint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) {{\n    const uint8_t *p;\n    p = (const uint8_t *)buf;\n    crc = crc ^ ~0U;\n    while (size--) {{\n        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);\n    }}\n    return crc ^ ~0U;\n}}\n"
        ),
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "fdb_calc_crc32");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert_eq!(report.globals.len(), 1);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit rust from real clang-lowered crc32 ir");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 0u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ crc.checked_shr("));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-flashdb-crc32-generic", rust);
}

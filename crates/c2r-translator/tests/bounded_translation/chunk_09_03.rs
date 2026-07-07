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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_parse_spec_emits_real_flashdb_crc32_from_lowered_ir_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let real_spec_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../validation/slice-specs/flashdb-real-fdb-calc-crc32.json");
    let real_spec: Value = serde_json::from_str(
        &fs::read_to_string(&real_spec_path).expect("read real fdb slice spec"),
    )
    .expect("parse real fdb slice spec");
    let source_file = "src/fdb_utils.c";
    let function_source_span = serde_json::from_value(
        real_spec
            .pointer("/c_boundary/signatures/0/source_span")
            .expect("function source span")
            .clone(),
    )
    .expect("parse function source span");
    let spec = SliceSpec {
        target_id: real_spec["target_id"].as_str().unwrap().to_string(),
        slice_id: real_spec["slice_id"].as_str().unwrap().to_string(),
        source_commit: real_spec["source_commit"].as_str().unwrap().to_string(),
        function_name: real_spec["function_name"].as_str().unwrap().to_string(),
        c_source: real_spec["c_source"].as_str().unwrap().to_string(),
        fixture_hash: real_spec["fixture_hash"].as_str().unwrap().to_string(),
        source_root: Some(
            real_spec["source"]["source_root"]
                .as_str()
                .unwrap()
                .to_string(),
        ),
        source_file: Some(source_file.to_string()),
        source_file_hashes: std::collections::BTreeMap::from([(
            source_file.to_string(),
            real_spec["source"]["source_file_hashes"][source_file]
                .as_str()
                .unwrap()
                .to_string(),
        )]),
        function_source_span: Some(function_source_span),
        build_profile: BuildProfile {
            include_paths: vec!["inc".to_string(), "tests".to_string()],
            defines: Vec::new(),
            target: None,
            clang_ast_fixture: None,
            target_triple: None,
            abi: None,
            compiler_command_source: "real-flashdb-slice-spec-test".to_string(),
            clang_available: true,
        },
        ..SliceSpec::default()
    };
    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_parse_spec_report(&environment, &parse_spec);

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.errors.is_empty(), "{:?}", report.errors);
    assert!(report.globals.iter().any(|global| {
        global.name == "crc32_table"
            && matches!(global.ty.kind, IrTypeKind::Array { len: Some(256), .. })
    }));
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit rust from real fdb clang-lowered ir");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 1996959894u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ crc.checked_shr("));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-flashdb-crc32-generic", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_array_subscript_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-array-subscript");
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
    let [IrStmt::Return {
        value: Some(IrExpr::Index {
            base, index, ty, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    assert!(matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "table"));
    assert!(matches!(index.as_ref(), IrExpr::Var { name, .. } if name == "idx"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_global_const_array_subscript_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-global-array-subscript");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
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
    let [IrStmt::Return {
        value: Some(IrExpr::Index { base, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected global array subscript return, got {:?}",
            function.body
        );
    };
    let IrExpr::Var { name, ty, .. } = base.as_ref() else {
        panic!("expected table variable, got {base:?}");
    };
    assert_eq!(name, "table");
    assert!(ty.is_const);
    assert!(matches!(ty.kind, IrTypeKind::Array { len: Some(256), .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_records_static_const_integer_array_global_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-global-array-initializer");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table_init.c");
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
    assert_eq!(report.globals.len(), 1);
    let global = &report.globals[0];
    assert_eq!(global.name, "table");
    assert!(global.ty.is_const);
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
fn clang_ast_dump_emits_typed_ir_for_loop_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-loop");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sum_to_limit.c");
    fs::write(
        &source_file,
        "int sum_to_limit(int limit) { int total = 0; for (int i = 0; i < limit; i++) { total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "sum_to_limit");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, .. }, IrStmt::For {
        init, step, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert_eq!(name, "total");
    assert!(matches!(init.as_slice(), [IrStmt::Decl { name, .. }] if name == "i"));
    assert!(matches!(step.as_deref(), Some(IrStmt::Assign { .. })));
    assert!(matches!(body.as_slice(), [IrStmt::Assign { .. }]));

    let rust = emit_rust_from_ir(function).expect("emit typed IR for loop from real clang AST");
    assert!(rust.contains("pub fn sum_to_limit(limit: i32) -> i32"));
    assert!(rust.contains("{\n        let mut i: i32 = 0i32;\n        while (i < limit) {"));
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\");"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-for-loop", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_for_continue_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-for-continue");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_for_continue.c");
    fs::write(
        &source_file,
        "int bad_for_continue(int limit) { int total = 0; for (int i = 0; i < limit; i++) { if (i) { continue; } total = total + i; } return total; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_for_continue");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { .. }, IrStmt::For { body, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!("expected decl, for, return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Continue { .. }])
    ));

    let rust = emit_rust_from_ir(function).expect("emit typed IR for continue from real clang AST");
    assert!(rust.contains("pub fn bad_for_continue(limit: i32) -> i32"));
    assert!(rust.contains("if i != 0i32 {"));
    assert!(
        rust.contains("                i = i.checked_add(1i32).expect(\"signed addition overflow\");\n                continue;"),
        "{rust:?}"
    );
    assert_eq!(
        rust.matches("i = i.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust:?}"
    );
    assert_rust_snippet_compiles("typed-ir-real-clang-for-continue", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_typed_ir_while_break_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-typed-ir-while-break");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("stop_at_limit.c");
    fs::write(
        &source_file,
        "int stop_at_limit(int value) { while (value) { if (value > 3) { break; } value = value - 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "stop_at_limit");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { body, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::If {
            then_body,
            ..
        }, IrStmt::Assign { .. }] if matches!(then_body.as_slice(), [IrStmt::Break { .. }])
    ));

    let rust = emit_rust_from_ir(function).expect("emit typed IR while break from real clang AST");
    assert!(rust.contains("pub fn stop_at_limit(mut value: i32) -> i32"));
    assert!(rust.contains("while value != 0i32 {"));
    assert!(rust.contains("if (value > 3i32) {"));
    assert!(rust.contains("break;"));
    assert!(
        rust.contains("value = value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-break", &rust);
}

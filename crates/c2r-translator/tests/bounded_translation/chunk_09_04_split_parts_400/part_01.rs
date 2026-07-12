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

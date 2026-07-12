#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_nested_record_field_inc_dec_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-record-field-inc-dec");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_nested_record_field_inc_dec.c");
    fs::write(
        &source_file,
        "struct inner { int x; };\nstruct outer { struct inner inner; int y; };\nint bad_nested_record_field_inc_dec(struct outer p) { p.inner.x++; return p.inner.x; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_nested_record_field_inc_dec",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert!(
        report.errors.iter().any(|error| error
            .message
            .contains("record field target must have a direct record variable base")),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_static_const_integer_array_global_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-global-array-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table_emit.c");
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
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit global table from clang typed IR");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(emitted
        .rust
        .contains("const TABLE: [u32; 4] = [1u32, 2u32, 3988292384u32, 4u32];"));
    assert!(emitted
        .rust
        .contains("pub fn read_global_table(idx: u32) -> u32"));
    assert!(emitted.rust.contains("return TABLE[idx as usize];"));
    assert!(!emitted.rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("clang_real_global_array_emit", &emitted.rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_records_static_const_incomplete_array_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-incomplete-global-array-init");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_incomplete_global_table_init.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[] = { 1U, 2U, 0xEDB88320U, 4U };\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
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
fn clang_ast_dump_does_not_synthesize_uninitialized_static_const_global_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-uninitialized-global-array");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_uninitialized_global_table.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[4];\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.globals.is_empty());
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect_err("uninitialized global table must not be synthesized");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("index base table is not declared"));
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_bitand_array_index_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-bitand-array-index");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_index.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_index(uint32_t crc, uint32_t idx) { return table[(crc ^ idx) & 0xff]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_index");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        rhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
    assert!(matches!(
        without_implicit_cast(rhs.as_ref()),
        IrExpr::LitInt { value: 255, .. }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_bitxor_bitnot_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-bitxor-bitnot-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_not.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_not(uint32_t crc) { crc = crc ^ ~0U; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_not");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected bitxor assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        lhs,
        rhs,
        ..
    } = value
    else {
        panic!("expected bitxor assignment value, got {value:?}");
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand,
        ..
    } = rhs.as_ref()
    else {
        panic!("expected bitnot rhs, got {rhs:?}");
    };
    assert!(matches!(operand.as_ref(), IrExpr::LitInt { value: 0, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_parenthesized_bitxor_bitnot_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-parenthesized-bitxor-bitnot-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_not_paren.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_not_paren(uint32_t crc) { crc = (crc ^ ~0U); return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_not_paren");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { value, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!(
            "expected parenthesized bitxor assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(
        value,
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_simple_while_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-simple-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_while(uint32_t crc) { while (crc) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_while");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "crc")
                && matches!(value, IrExpr::Var { name, .. } if name == "crc")
    ));
}

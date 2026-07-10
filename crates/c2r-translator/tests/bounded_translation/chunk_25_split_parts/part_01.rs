#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_distinct_record_pointer_compound_read_wraps_and_runs() {
    let function_name = "advance_walk_cursor";
    let ast = distinct_record_pointer_compound_read_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower renamed distinct record-pointer compound read");

    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Member { field, is_arrow: true, .. } if field == "walked")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, rhs, .. }
                    if matches!(rhs.as_ref(), IrExpr::LValueToRValue { expr, .. }
                        if matches!(expr.as_ref(), IrExpr::Member {
                            field,
                            is_arrow: true,
                            ..
                        } if field == "step_size")))
    ));

    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        distinct_record_pointer_compound_read_policy(),
    )
    .expect("emit renamed distinct record-pointer compound read");
    let rust = &emitted.rust;
    assert!(
        rust.contains("cursor.walked = cursor.walked.wrapping_add(ledger.step_size);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-distinct-record-pointer-compound-read",
        rust,
        r#"
    let ledger = StepLedger { step_size: 3 };
    let mut cursor = WalkCursor { walked: u32::MAX - 1 };
    advance_walk_cursor(&ledger, &mut cursor);
    assert_eq!(cursor.walked, 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_distinct_record_pointer_compound_read_wraps_and_runs() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-distinct-record-pointer-compound-read");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("advance_walk_cursor.c");
    fs::write(
        &source_file,
        "struct StepLedger { unsigned int step_size; };\n\
         struct WalkCursor { unsigned int walked; };\n\
         void advance_walk_cursor(struct StepLedger *ledger, struct WalkCursor *cursor) {\n\
             cursor->walked += ledger->step_size;\n\
         }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);
    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "advance_walk_cursor",
    );
    assert_eq!(report.status, "lowered", "{:?}", report.errors);

    let emitted = emit_rust_from_ir_with_globals_and_policy(
        report.function_ir.as_ref().expect("real clang function IR"),
        &report.globals,
        distinct_record_pointer_compound_read_policy(),
    )
    .expect("emit real-clang distinct record-pointer compound read");
    let rust = &emitted.rust;
    assert!(
        rust.contains("cursor.walked = cursor.walked.wrapping_add(ledger.step_size);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-real-clang-distinct-record-pointer-compound-read",
        rust,
        r#"
    let ledger = StepLedger { step_size: 5 };
    let mut cursor = WalkCursor { walked: u32::MAX - 2 };
    advance_walk_cursor(&ledger, &mut cursor);
    assert_eq!(cursor.walked, 2);
"#,
    );
}

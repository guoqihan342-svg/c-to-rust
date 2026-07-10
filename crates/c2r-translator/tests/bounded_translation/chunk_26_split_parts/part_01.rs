#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_lowers_emits_and_runs() {
    let function_name = "clear_nested_offset";
    let ast = nested_literal_field_assignment_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower renamed nested literal field assignment");

    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Member {
                field,
                is_arrow: false,
                base,
                ..
            } if field == "offset" && matches!(base.as_ref(), IrExpr::Member {
                field,
                is_arrow: true,
                ..
            } if field == "position"))
                && matches!(value, IrExpr::Cast { expr, .. }
                    if matches!(expr.as_ref(), IrExpr::LitInt { value: 0, .. }))
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed nested literal field assignment");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        emitted.rust.contains("ctx.position.offset = (0i32 as u32);")
            || emitted.rust.contains("ctx.position.offset = 0u32;"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs(
        "typed-ir-nested-literal-field-assignment",
        &emitted.rust,
        r#"
    let mut ctx = Session {
        position: Coordinate { offset: u32::MAX, guard: 73 },
        marker: 91,
    };
    clear_nested_offset(&mut ctx);
    assert_eq!(ctx.position.offset, 0);
    assert_eq!(ctx.position.guard, 73);
    assert_eq!(ctx.marker, 91);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_nested_literal_field_assignment_lowers_emits_and_runs() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-literal-field-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("clear_nested_offset.c");
    fs::write(
        &source_file,
        "struct Coordinate { unsigned int offset; unsigned int guard; };\n\
         struct Session { struct Coordinate position; unsigned int marker; };\n\
         void clear_nested_offset(struct Session *ctx) {\n\
             ctx->position.offset = 0;\n\
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
        "clear_nested_offset",
    );
    assert_eq!(report.status, "lowered", "{:?}", report.errors);

    let emitted = emit_rust_from_ir_with_globals(
        report.function_ir.as_ref().expect("real clang function IR"),
        &report.globals,
    )
    .expect("emit real-clang nested literal field assignment");
    assert!(
        emitted.rust.contains("ctx.position.offset = (0i32 as u32);")
            || emitted.rust.contains("ctx.position.offset = 0u32;"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs(
        "typed-ir-real-clang-nested-literal-field-assignment",
        &emitted.rust,
        r#"
    let mut ctx = Session {
        position: Coordinate { offset: 17, guard: 31 },
        marker: 47,
    };
    clear_nested_offset(&mut ctx);
    assert_eq!(ctx.position.offset, 0);
    assert_eq!(ctx.position.guard, 31);
    assert_eq!(ctx.marker, 47);
"#,
    );
}

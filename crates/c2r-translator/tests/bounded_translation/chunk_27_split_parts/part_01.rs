#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_lowers_emits_and_wraps() {
    let function_name = "advance_nested_value";
    let ast = nested_record_scalar_add_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower renamed nested record scalar add");
    let IrTypeKind::Record {
        fields: Some(source_fields),
        ..
    } = &lowered.function_ir.params[1].ty.kind
    else {
        panic!("by-value source must retain complete record inventory");
    };
    assert!(source_fields.iter().any(|field| field.name == "base"));
    assert!(source_fields.iter().any(|field| field.name == "guard"));

    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Member {
                field,
                is_arrow: false,
                base,
                ..
            } if field == "value" && matches!(base.as_ref(), IrExpr::Member {
                field,
                is_arrow: true,
                ..
            } if field == "nested"))
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, lhs, rhs, .. }
                    if matches!(lhs.as_ref(), IrExpr::LValueToRValue { expr, .. }
                        if matches!(expr.as_ref(), IrExpr::Member {
                            field,
                            is_arrow: false,
                            ..
                        } if field == "base"))
                    && matches!(rhs.as_ref(), IrExpr::LValueToRValue { expr, .. }
                        if matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "extent")))
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed nested record scalar add");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        emitted
            .rust
            .contains("target.nested.value = source.base.wrapping_add(extent);"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs(
        "typed-ir-nested-record-scalar-add",
        &emitted.rust,
        r#"
    let mut target = Output {
        nested: Cell { value: 41, guard: 73 },
        marker: 91,
    };
    let source = Input { base: u32::MAX - 2 };
    advance_nested_value(&mut target, source, 5);
    assert_eq!(target.nested.value, 2);
    assert_eq!(target.nested.guard, 73);
    assert_eq!(target.marker, 91);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_nested_record_scalar_add_lowers_emits_and_wraps() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-record-scalar-add");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("advance_nested_value.c");
    fs::write(
        &source_file,
        "struct Cell { unsigned int value; unsigned int guard; };\n\
         struct Output { struct Cell nested; unsigned int marker; };\n\
         struct Input { unsigned int base; unsigned int guard; };\n\
         void advance_nested_value(struct Output *target, struct Input source,\n\
                                   unsigned int extent) {\n\
             target->nested.value = source.base + extent;\n\
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
        "advance_nested_value",
    );
    assert_eq!(report.status, "lowered", "{:?}", report.errors);

    let emitted = emit_rust_from_ir_with_globals(
        report.function_ir.as_ref().expect("real clang function IR"),
        &report.globals,
    )
    .expect("emit real-clang nested record scalar add");
    assert!(
        emitted
            .rust
            .contains("target.nested.value = source.base.wrapping_add(extent);"),
        "{}",
        emitted.rust
    );
    assert_rust_snippet_runs(
        "typed-ir-real-clang-nested-record-scalar-add",
        &emitted.rust,
        r#"
    let mut target = Output {
        nested: Cell { value: 13, guard: 17 },
        marker: 19,
    };
    let source = Input { base: u32::MAX };
    advance_nested_value(&mut target, source, 2);
    assert_eq!(target.nested.value, 1);
    assert_eq!(target.nested.guard, 17);
    assert_eq!(target.marker, 19);
"#,
    );
}

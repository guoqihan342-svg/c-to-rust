#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_conditional_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-conditional-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pick_init.c");
    fs::write(
        &source_file,
        "int pick_init(int flag, int left, int right) { int out = flag ? left : right; return out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "pick_init");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Conditional { .. }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected conditional decl initializer followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit conditional decl initializer from real clang AST");
    assert!(rust.contains("pub fn pick_init(flag: i32, left: i32, right: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if flag != 0i32 { left } else { right });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-conditional-decl", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_conditional_assignment_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-conditional-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pick_assign.c");
    fs::write(
        &source_file,
        "int pick_assign(int flag, int value, int fallback) { value = flag ? value : fallback; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "pick_assign");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Conditional { .. },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected conditional assignment followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit conditional assignment from real clang AST");
    assert!(rust.contains("pub fn pick_assign(flag: i32, mut value: i32, fallback: i32) -> i32"));
    assert!(rust.contains("value = (if flag != 0i32 { value } else { fallback });"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-conditional-assign", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_conditional_branch_integral_cast_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-conditional-cast");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("choose_u32.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t choose_u32(uint32_t flag, uint32_t value) { return flag ? value : 2; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "choose_u32");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Conditional { else_expr, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned conditional return, got {:?}",
            function.body
        );
    };
    assert!(matches!(
        else_expr.as_ref(),
        IrExpr::Cast { implicit: true, .. }
    ));

    let rust =
        emit_rust_from_ir(function).expect("emit unsigned conditional return from real clang AST");
    assert!(rust.contains("pub fn choose_u32(flag: u32, value: u32) -> u32"));
    assert!(rust.contains("return (if flag != 0u32 { value } else { (2i32 as u32) });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-unsigned-conditional-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_binary_conditional_operator_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-binary-conditional");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_gnu_conditional.c");
    fs::write(
        &source_file,
        "int bad_gnu_conditional(int value, int fallback) { return value ?: fallback; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "bad_gnu_conditional",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert_eq!(
        report.errors.first().map(|error| error.kind.as_str()),
        Some("unsupported_clang_expr")
    );
    assert!(
        report
            .errors
            .first()
            .map(|error| error.message.contains("BinaryConditionalOperator"))
            .unwrap_or(false),
        "{:?}",
        report.errors
    );
}

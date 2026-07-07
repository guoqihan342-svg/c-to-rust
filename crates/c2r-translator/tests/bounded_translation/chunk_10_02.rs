#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_positive.c");
    fs::write(
        &source_file,
        "int adjust_positive(int value) { if (value > 0) { value = value + 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "adjust_positive");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::Gt, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected comparison if followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit comparison if from real clang AST");
    assert!(rust.contains("pub fn adjust_positive(mut value: i32) -> i32"));
    assert!(rust.contains("if (value > 0i32) {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("positive_as_int.c");
    fs::write(
        &source_file,
        "int positive_as_int(int value) { return value > 0; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "positive_as_int");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary {
            op: IrBinOp::Gt, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected comparison return, got {:?}", function.body);
    };

    let rust = emit_rust_from_ir(function).expect("emit comparison return from real clang AST");
    assert!(rust.contains("pub fn positive_as_int(value: i32) -> i32"));
    assert!(rust.contains("return (if (value > 0i32) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-return-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_null_pointer_comparison_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-null-pointer-comparison-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("has_values.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\nint has_values(const int *values) { return values != NULL; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "has_values");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Neq,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected null pointer comparison return, got {:?}",
            function.body
        );
    };
    assert!(matches!(rhs.as_ref(), IrExpr::NullPtr { .. }));

    let rust = emit_rust_from_ir(function)
        .expect("emit null pointer comparison return from real clang AST");
    assert!(rust.contains("pub fn has_values(values: Option<&[i32]>) -> i32"));
    assert!(rust.contains("return (if values.is_some() { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-return-null-pointer-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_record_null_pointer_comparison_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-record-null-pointer-comparison-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("has_point.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\n\
         struct point { int x; };\n\
         int has_point(const struct point *p) { return p != NULL; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "has_point");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Neq,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected record null pointer comparison return, got {:?}",
            function.body
        );
    };
    assert!(matches!(rhs.as_ref(), IrExpr::NullPtr { .. }));

    let emitted = emit_rust_from_ir(function)
        .expect("emit record null pointer comparison return from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub x: i32"), "{rust}");
    assert!(
        rust.contains("pub fn has_point(p: Option<&Point>) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return (if p.is_some() { 1i32 } else { 0i32 });"),
        "{rust}"
    );
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-return-record-null-pointer-comparison",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("cmp_init.c");
    fs::write(
        &source_file,
        "int cmp_init(int left, int right) { int out = left == right; return out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "cmp_init");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Binary {
            op: IrBinOp::Eq, ..
        }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected comparison decl initializer followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit comparison decl initializer from real clang AST");
    assert!(rust.contains("pub fn cmp_init(left: i32, right: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if (left == right) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-decl-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_comparison_assignment_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-comparison-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("cmp_assign.c");
    fs::write(
        &source_file,
        "int cmp_assign(int left, int right) { left = left != right; return left; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "cmp_assign");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Binary {
            op: IrBinOp::Neq, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected comparison assignment followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit comparison assignment from real clang AST");
    assert!(rust.contains("pub fn cmp_assign(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains("left = (if (left != right) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return left;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-assign-comparison", &rust);
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_conditional_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-conditional-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pick.c");
    fs::write(
        &source_file,
        "int pick(int flag, int left, int right) { return flag ? left : right; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "pick");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Conditional { .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected conditional return, got {:?}", function.body);
    };

    let rust = emit_rust_from_ir(function).expect("emit conditional return from real clang AST");
    assert!(rust.contains("pub fn pick(flag: i32, left: i32, right: i32) -> i32"));
    assert!(rust.contains("return (if flag != 0i32 { left } else { right });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-conditional-return", &rust);
}

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

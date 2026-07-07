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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_while_without_braces_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-while-without-braces");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("countdown_no_braces.c");
    fs::write(
        &source_file,
        "int countdown_no_braces(int value) { while (value > 0) value = value + ~0; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "countdown_no_braces",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::Gt,
            ..
        }
    ));
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit no-brace while from real clang AST");
    assert!(rust.contains("pub fn countdown_no_braces(mut value: i32) -> i32"));
    assert!(rust.contains("while (value > 0i32) {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-without-braces", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_simple_if_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-simple-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_if.c");
    fs::write(
        &source_file,
        "int adjust_if(int value, int flag) { if (flag) { value = value + 1; } else { value = value + ~0; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "adjust_if");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit simple if from real clang AST");
    assert!(rust.contains("pub fn adjust_if(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_if_without_braces_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-if-without-braces");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_if_no_braces.c");
    fs::write(
        &source_file,
        "int adjust_if_no_braces(int value, int flag) { if (flag) value = value + 1; else value = value + ~0; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "adjust_if_no_braces",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { value, .. }] if matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { value, .. }] if matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit no-brace if from real clang AST");
    assert!(rust.contains("pub fn adjust_if_no_braces(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = value.checked_add(!0i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-without-braces", &rust);
}

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

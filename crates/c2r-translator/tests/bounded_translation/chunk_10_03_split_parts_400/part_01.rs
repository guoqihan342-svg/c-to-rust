#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_compound_assignment_integer_promotion_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-compound-assignment-integer-promotion");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("inc8.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t compound_assignment_integer_promotion(uint8_t value) { value += 1; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "compound_assignment_integer_promotion",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected promoted compound assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
    let IrExpr::Cast {
        target: cast_target,
        expr,
        implicit: true,
        ..
    } = value
    else {
        panic!("expected compound assignment final cast, got {value:?}");
    };
    assert!(matches!(
        &cast_target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
    assert!(matches!(
        expr.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Add,
            ty,
            ..
        } if matches!(&ty.kind, IrTypeKind::Integer { signed: true, width: 32 })
    ));

    let rust =
        emit_rust_from_ir(function).expect("emit promoted compound assignment from real clang AST");
    assert!(rust.contains("pub fn compound_assignment_integer_promotion(mut value: u8) -> u8"));
    assert!(rust.contains(
        "value = ((value as i32).checked_add(1i32).expect(\"signed addition overflow\") as u8);"
    ));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-compound-promotion", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("is_zero_value.c");
    fs::write(
        &source_file,
        "int is_zero_value(int value) { return !value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "is_zero_value");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Unary {
            op: IrUnOp::Not, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected logical not return, got {:?}", function.body);
    };

    let rust = emit_rust_from_ir(function).expect("emit logical not return from real clang AST");
    assert!(rust.contains("pub fn is_zero_value(value: i32) -> i32"));
    assert!(rust.contains("return (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-return-logical-not", &rust);
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("init_is_zero.c");
    fs::write(
        &source_file,
        "int init_is_zero(int value) { int out = !value; return out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "init_is_zero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Unary {
            op: IrUnOp::Not, ..
        }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected logical not decl initializer followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit logical not decl initializer from real clang AST");
    assert!(rust.contains("pub fn init_is_zero(value: i32) -> i32"));
    assert!(rust.contains("let mut out: i32 = (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return out;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-decl-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_assignment_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("normalize_zero.c");
    fs::write(
        &source_file,
        "int normalize_zero(int value) { value = !value; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "normalize_zero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Unary {
            op: IrUnOp::Not, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected logical not assignment followed by return, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit logical not assignment from real clang AST");
    assert!(rust.contains("pub fn normalize_zero(mut value: i32) -> i32"));
    assert!(rust.contains("value = (if value == 0i32 { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-assign-logical-not", &rust);
}

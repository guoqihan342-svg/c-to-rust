#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_assignment_rhs_integral_cast_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-assignment-rhs-cast");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("set_unsigned_one.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t set_unsigned_one(uint32_t value) { value = 1; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "set_unsigned_one");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign {
        value: IrExpr::Cast { implicit: true, .. },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned assignment RHS cast followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit unsigned assignment RHS integral cast");
    assert!(rust.contains("pub fn set_unsigned_one(mut value: u32) -> u32"));
    assert!(rust.contains("value = (1i32 as u32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-assign-rhs-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_decl_and_return_integral_casts_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-decl-return-casts");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("unsigned_decl_return.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t unsigned_decl_return(void) { uint32_t value = 1; return 2; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "unsigned_decl_return",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Cast { implicit: true, .. }),
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Cast { implicit: true, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned decl initializer and return casts, got {:?}",
            function.body
        );
    };

    let rust =
        emit_rust_from_ir(function).expect("emit unsigned decl initializer and return casts");
    assert!(rust.contains("pub fn unsigned_decl_return() -> u32"));
    assert!(rust.contains("let mut value: u32 = (1i32 as u32);"));
    assert!(rust.contains("return (2i32 as u32);"));
    assert_rust_snippet_compiles("typed-ir-real-clang-decl-return-casts", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_logical_not_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-logical-not-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("is_zero.c");
    fs::write(
        &source_file,
        "int is_zero(int value) { if (!value) { return 1; } return 0; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "is_zero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition: IrExpr::Unary {
            op: IrUnOp::Not, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected logical not if followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit logical not if from real clang AST");
    assert!(rust.contains("pub fn is_zero(value: i32) -> i32"));
    assert!(rust.contains("if value == 0i32 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-logical-not", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_short_circuit_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-short-circuit-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("both_nonzero.c");
    fs::write(
        &source_file,
        "int both_nonzero(int left, int right) { if (left && right) { return 1; } return 0; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "both_nonzero");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::LogAnd,
            ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected short-circuit if followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit short-circuit if from real clang AST");
    assert!(rust.contains("pub fn both_nonzero(left: i32, right: i32) -> i32"));
    assert!(rust.contains("if (left != 0i32 && right != 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-short-circuit", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_short_circuit_value_positions_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-short-circuit-values");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("short_circuit_values.c");
    fs::write(
        &source_file,
        "int short_circuit_values(int left, int right) { int out = left || right; left = left && (right > 0); return left || out; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "short_circuit_values",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        init: Some(IrExpr::Binary {
            op: IrBinOp::LogOr, ..
        }),
        ..
    }, IrStmt::Assign {
        value: IrExpr::Binary {
            op: IrBinOp::LogAnd,
            ..
        },
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Binary {
            op: IrBinOp::LogOr, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected short-circuit decl, assignment, and return values, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit short-circuit values from real clang AST");
    assert!(rust.contains("pub fn short_circuit_values(mut left: i32, right: i32) -> i32"));
    assert!(rust.contains(
        "let mut out: i32 = (if (left != 0i32 || right != 0i32) { 1i32 } else { 0i32 });"
    ));
    assert!(rust.contains("left = (if (left != 0i32 && (right > 0i32)) { 1i32 } else { 0i32 });"));
    assert!(rust.contains("return (if (left != 0i32 || out != 0i32) { 1i32 } else { 0i32 });"));
    assert_rust_snippet_compiles("typed-ir-real-clang-short-circuit-values", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_scalar_compound_assignment_family_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-compound-assignment-family");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("compound_family.c");
    fs::write(
        &source_file,
        "int compound_family(int value) { value += 1; value -= 2; value *= 3; value /= 4; value %= 5; value &= 7; value |= 8; value ^= 9; value <<= 1; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "compound_family");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert_eq!(function.body.len(), 10, "{:?}", function.body);
    for (stmt, expected_op) in function.body.iter().take(9).zip([
        IrBinOp::Add,
        IrBinOp::Sub,
        IrBinOp::Mul,
        IrBinOp::Div,
        IrBinOp::Mod,
        IrBinOp::BitAnd,
        IrBinOp::BitOr,
        IrBinOp::BitXor,
        IrBinOp::Shl,
    ]) {
        let IrStmt::Assign { target, value, .. } = stmt else {
            panic!("expected desugared compound assignment, got {stmt:?}");
        };
        assert!(matches!(target, IrExpr::Var { name, .. } if name == "value"));
        assert!(
            matches!(value, IrExpr::Binary { op, .. } if *op == expected_op),
            "{value:?}"
        );
    }

    let rust =
        emit_rust_from_ir(function).expect("emit scalar compound assignments from real clang AST");
    assert!(rust.contains("pub fn compound_family(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(
        rust.contains("value = value.checked_sub(2i32).expect(\"signed subtraction overflow\");")
    );
    assert!(rust
        .contains("value = value.checked_mul(3i32).expect(\"signed multiplication overflow\");"));
    assert!(rust.contains(
        "value = value.checked_div(4i32).expect(\"division by zero or signed overflow\");"
    ));
    assert!(rust.contains(
        "value = value.checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"
    ));
    assert!(rust.contains("value = (value & 7i32);"));
    assert!(rust.contains("value = (value | 8i32);"));
    assert!(rust.contains("value = (value ^ 9i32);"));
    assert!(rust.contains("value = value.checked_shl(core::convert::TryFrom::try_from(1i32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-compound-family", &rust);
}

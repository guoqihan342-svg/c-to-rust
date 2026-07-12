#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_unsigned_comparison_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-unsigned-comparison-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_unsigned_positive.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t adjust_unsigned_positive(uint32_t value) { if (value > 0) { value = value + 1U; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "adjust_unsigned_positive",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition:
            IrExpr::Binary {
                op: IrBinOp::Gt,
                rhs,
                ..
            },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned comparison if followed by return, got {:?}",
            function.body
        );
    };
    assert!(
        matches!(rhs.as_ref(), IrExpr::Cast { implicit: true, .. }),
        "expected clang integral cast on unsigned comparison literal, got {rhs:?}"
    );

    let rust =
        emit_rust_from_ir(function).expect("emit unsigned comparison if from real clang AST");
    assert!(rust.contains("pub fn adjust_unsigned_positive(mut value: u32) -> u32"));
    assert!(rust.contains("if (value > (0i32 as u32)) {"));
    assert!(rust.contains("value = value.wrapping_add(1u32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-unsigned-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_signed_char_binary_promotion_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-signed-char-binary-promotion");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("signed_char_add_one.c");
    fs::write(
        &source_file,
        "int signed_char_add_one(signed char value) { return value + 1; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "signed_char_add_one",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary { lhs, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected signed char binary promotion return, got {:?}",
            function.body
        );
    };
    assert!(
        matches!(lhs.as_ref(), IrExpr::Cast { implicit: true, .. }),
        "expected clang integral promotion cast on signed char lhs, got {lhs:?}"
    );

    let rust = emit_rust_from_ir(function).expect("emit signed char binary promotion");
    assert!(rust.contains("pub fn signed_char_add_one(value: i8) -> i32"));
    assert!(rust
        .contains("return (value as i32).checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-real-clang-signed-char-promotion", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_postfix_increment_if_condition_in_scalar_emitter_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-if-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_if_postinc.c");
    fs::write(
        &source_file,
        "int bad_if_postinc(int value) { if (value++) { value = value; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_if_postinc");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error =
        emit_rust_from_ir(function).expect_err("postfix increment if condition must fail closed");
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_postfix_decrement_while_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-decrement-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while_size.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t crc_while_size(uint32_t crc, size_t size) { while (size--) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_while_size");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ..
    } = condition
    else {
        panic!("expected postfix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_postfix_decrement_while_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-decrement-while-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_while_size.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\nint bad_while_size(int value, size_t size) { while (size--) { value = value; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_while_size");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit postfix decrement while condition");
    assert!(rust.contains("pub fn bad_while_size(mut value: i32, mut size: usize) -> i32"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("let size_before_dec0: usize = size;"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size_before_dec0 == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("value = value;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-postfix-decrement-while", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_prefix_decrement_while_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-decrement-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while_prefix_size.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t crc_while_prefix_size(uint32_t crc, size_t size) { while (--size) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "crc_while_prefix_size",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit prefix decrement while condition");
    assert!(rust.contains("pub fn crc_while_prefix_size(mut crc: u32, mut size: usize) -> u32"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("crc = crc;"));
    assert!(rust.contains("return crc;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-prefix-decrement-while", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_prefix_increment_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-increment-return");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("prefix_return.c");
    fs::write(
        &source_file,
        "int prefix_return(int value) { return ++value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "prefix_return");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit prefix increment return value");
    assert!(rust.contains("pub fn prefix_return(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-prefix-increment-return",
        &rust,
        "    assert_eq!(prefix_return(5), 6);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_postfix_increment_decl_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("postfix_decl.c");
    fs::write(
        &source_file,
        "int postfix_decl(int value) { int out = value++; return out + value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "postfix_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit postfix increment decl initializer");
    assert!(rust.contains("pub fn postfix_decl(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("let mut out: i32 = post_inc_value;"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-postfix-increment-decl",
        &rust,
        "    assert_eq!(postfix_decl(5), 11);",
    );
}

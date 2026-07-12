#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_prefix_increment_call_argument_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-increment-call-arg");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("prefix_call_arg.c");
    fs::write(
        &source_file,
        "int helper(int value) { return value * 2; }\nint prefix_call_arg(int value) { return helper(++value); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "prefix_call_arg");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit prefix increment call argument");
    assert!(rust.contains("pub fn prefix_call_arg(mut value: i32) -> i32"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(value);"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-prefix-increment-call-arg",
        &format!(
            "fn helper(value: i32) -> i32 {{ value * 2 }}\n{}",
            rust.rust
        ),
        "    assert_eq!(prefix_call_arg(5), 12);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_postfix_increment_call_argument_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-call-arg");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("postfix_call_arg.c");
    fs::write(
        &source_file,
        "int helper(int value) { return value * 2; }\nint postfix_call_arg(int value) { return helper(value++); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "postfix_call_arg");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit postfix increment call argument");
    assert!(rust.contains("pub fn postfix_call_arg(mut value: i32) -> i32"));
    assert!(rust.contains("let post_inc_value: i32 = value;"));
    assert!(rust.contains("value = value.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return helper(post_inc_value);"));
    assert_rust_snippet_runs(
        "typed-ir-real-clang-postfix-increment-call-arg",
        &format!(
            "fn helper(value: i32) -> i32 {{ value * 2 }}\n{}",
            rust.rust
        ),
        "    assert_eq!(postfix_call_arg(5), 10);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_prefix_increment_deref_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-prefix-increment-deref");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_prefix_inc.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_prefix_inc(const uint8_t *p) { return *++p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "read_byte_prefix_inc",
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
            .map(|error| {
                error
                    .message
                    .contains("deref pointer cannot use prefix increment/decrement value semantics")
            })
            .unwrap_or(false),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_integral_c_style_cast_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-integral-cast");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("narrow.c");
    fs::write(
        &source_file,
        "unsigned int narrow(unsigned long value) { return (unsigned int)value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "narrow");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit integral C-style cast");
    assert!(rust.contains("pub fn narrow(value: u64) -> u32"));
    assert!(rust.contains("return (value as u32);"));
    assert_rust_snippet_compiles("typed-ir-real-clang-integral-c-style-cast", &rust);
}

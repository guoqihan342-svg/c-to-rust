#[cfg(feature = "typed-ir")]
fn assert_rust_snippet_runs_with_overflow_checks(
    name: &str,
    rust_code: &str,
    main_body: &str,
    overflow_checks: bool,
) {
    let out_dir = unique_out_dir(name);
    fs::create_dir_all(&out_dir).unwrap();
    let source = out_dir.join("main.rs");
    let output = out_dir.join(if cfg!(windows) { "main.exe" } else { "main" });
    fs::write(
        &source,
        format!("{rust_code}\nfn main() {{\n{main_body}\n}}\n"),
    )
    .unwrap();

    let rustc = std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into());
    let compile = Command::new(&rustc)
        .arg("-Awarnings")
        .arg("-C")
        .arg(if overflow_checks {
            "overflow-checks=on"
        } else {
            "overflow-checks=off"
        })
        .arg(&source)
        .arg("-o")
        .arg(&output)
        .output()
        .unwrap_or_else(|error| panic!("failed to run rustc: {error}"));

    assert!(
        compile.status.success(),
        "rustc failed for {name}\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&compile.stdout),
        String::from_utf8_lossy(&compile.stderr)
    );

    let run = Command::new(&output)
        .output()
        .unwrap_or_else(|error| panic!("failed to run emitted snippet {name}: {error}"));
    assert!(
        run.status.success(),
        "emitted snippet failed for {name}\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&run.stdout),
        String::from_utf8_lossy(&run.stderr)
    );

    fs::remove_dir_all(out_dir).unwrap();
}

#[cfg(feature = "typed-ir")]
fn assert_rust_snippet_fails_with_overflow_checks(
    name: &str,
    rust_code: &str,
    main_body: &str,
    overflow_checks: bool,
) {
    let out_dir = unique_out_dir(name);
    fs::create_dir_all(&out_dir).unwrap();
    let source = out_dir.join("main.rs");
    let output = out_dir.join(if cfg!(windows) { "main.exe" } else { "main" });
    fs::write(
        &source,
        format!("{rust_code}\nfn main() {{\n{main_body}\n}}\n"),
    )
    .unwrap();

    let rustc = std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into());
    let compile = Command::new(&rustc)
        .arg("-Awarnings")
        .arg("-C")
        .arg(if overflow_checks {
            "overflow-checks=on"
        } else {
            "overflow-checks=off"
        })
        .arg(&source)
        .arg("-o")
        .arg(&output)
        .output()
        .unwrap_or_else(|error| panic!("failed to run rustc: {error}"));

    assert!(
        compile.status.success(),
        "rustc failed for {name}\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&compile.stdout),
        String::from_utf8_lossy(&compile.stderr)
    );

    let run = Command::new(&output)
        .output()
        .unwrap_or_else(|error| panic!("failed to run emitted snippet {name}: {error}"));
    assert!(
        !run.status.success(),
        "emitted snippet unexpectedly succeeded for {name}\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&run.stdout),
        String::from_utf8_lossy(&run.stderr)
    );

    fs::remove_dir_all(out_dir).unwrap();
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_without_clang_path_to_typed_ir_and_rust() {
    let ast: Value = serde_json::from_str(include_str!("../../../fixtures/clang_ast/add_one_ast.json"))
        .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "add_one")
        .expect("lower committed clang AST fixture");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from fixture typed IR");
    let rust = &emitted.rust;

    assert!(lowered.globals.is_empty());
    assert!(rust.contains("pub fn add_one(value: i32) -> i32"), "{rust}");
    assert!(
        rust.contains("return value.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-add-one", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_direct_call_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../../fixtures/clang_ast/direct_call_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "call_expression")
        .expect("lower direct call fixture without invoking clang");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from direct call fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn call_expression(mut value: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let mut first: i32 = helper(value);"),
        "{rust}"
    );
    assert!(rust.contains("value = helper(first);"), "{rust}");
    assert!(rust.contains("return helper(value);"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-direct-call",
        &format!("fn helper(value: i32) -> i32 {{ value }}\n{rust}"),
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_call_expression_chain_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../../fixtures/clang_ast/call_expression_chain_ast.json"))
            .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "call_expression_chain")
            .expect("lower recursive direct call fixture without invoking clang");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from recursive call fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn call_expression_chain(mut value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("if (value <= 0i32)"), "{rust}");
    assert!(rust.contains("return (-value);"), "{rust}");
    assert!(
        rust.contains("let mut first: i32 = call_expression_chain(value.checked_sub(1i32)"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-call-expression-chain",
        rust,
        "\
        assert_eq!(call_expression_chain(-2), 2);\n\
        assert_eq!(call_expression_chain(0), 0);\n\
        assert_eq!(call_expression_chain(1), 0);\n\
        assert_eq!(call_expression_chain(3), 0);\n\
        ",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_abs_int_model_without_clang() {
    let ast: Value = serde_json::from_str(include_str!("../../../fixtures/clang_ast/abs_call_ast.json"))
        .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "abs_value")
        .expect("lower abs(int) fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(IrExpr::Call {
            callee, args, ty, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected abs return call, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(callee, "abs");
    assert_eq!(args.len(), 1);
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit modeled abs(int) from fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn abs_value(value: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return value.checked_abs().expect(\"C abs(int) precondition violated\");"),
        "{rust}"
    );
    assert!(!rust.contains("abs(value)"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-abs-int", rust);
}

use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

#[cfg(feature = "typed-ir")]
use std::process::Command;

#[cfg(feature = "clang-frontend")]
use c2r_translator::clang_frontend::ClangParseSpec;
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
use c2r_translator::clang_frontend::{
    lower_function_and_globals_from_clang_ast_json_value,
    lower_function_and_globals_from_clang_ast_json_value_with_target_abi,
    lower_function_from_clang_ast_dump, lower_function_from_clang_ast_dump_report,
    lower_function_from_clang_parse_spec_report, lower_function_skeleton,
    lower_function_skeleton_report, resolve_clang_path, ClangBinaryOperator, ClangExprSkeleton,
    ClangFunctionSkeleton, ClangIncDecOperator, ClangParamSkeleton, ClangStmtSkeleton,
    ClangTypeKind, ClangTypeSkeleton, ClangUnaryOperator,
};
#[cfg(feature = "typed-ir")]
use c2r_translator::translation_route::{CandidateGenerator, CandidateRoute};
#[cfg(feature = "typed-ir")]
use c2r_translator::typed_ir::{
    emit_rust_from_ir, emit_rust_from_ir_with_globals, emit_rust_from_ir_with_globals_and_policy,
    EmitPolicy, IrBinOp, IrExpr, IrFunction, IrGlobal, IrGlobalInit, IrIncDecOp, IrParam,
    IrRecordField, IrStmt, IrType, IrTypeKind, IrUnOp, NoAliasParamPair, SignedRightShiftPolicy,
};
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
use c2r_translator::TargetAbiProfile;
use c2r_translator::{write_translation_artifacts, BuildProfile, SliceSpec};
use serde_json::Value;

fn profile(clang_available: bool) -> BuildProfile {
    BuildProfile {
        include_paths: vec!["/tmp/lib/include".to_string()],
        defines: vec!["_GNU_SOURCE".to_string()],
        target: None,
        clang_ast_fixture: None,
        target_triple: Some("x86_64-unknown-linux-gnu".to_string()),
        abi: Some("linux-gnu".to_string()),
        compiler_command_source: "compile_commands.json".to_string(),
        clang_available,
    }
}

fn unique_out_dir(name: &str) -> PathBuf {
    std::env::temp_dir().join(format!(
        "c2r-translator-test-{name}-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

fn json_file(path: PathBuf) -> Value {
    serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
}

#[test]
fn real_clang_ast_tests_use_shared_visible_gate() {
    let source = concat!(
        include_str!("chunk_00_00.rs"),
        include_str!("chunk_00_01.rs"),
        include_str!("chunk_00_02.rs"),
        include_str!("chunk_00_03.rs"),
        include_str!("chunk_00_04.rs"),
        include_str!("chunk_01_00.rs"),
        include_str!("chunk_01_01.rs"),
        include_str!("chunk_01_02.rs"),
        include_str!("chunk_01_03.rs"),
        include_str!("chunk_01_04.rs"),
        include_str!("chunk_02_00.rs"),
        include_str!("chunk_02_01.rs"),
        include_str!("chunk_02_02.rs"),
        include_str!("chunk_02_03.rs"),
        include_str!("chunk_02_04.rs"),
        include_str!("chunk_03_00.rs"),
        include_str!("chunk_03_01.rs"),
        include_str!("chunk_03_02.rs"),
        include_str!("chunk_03_03.rs"),
        include_str!("chunk_03_04.rs"),
        include_str!("chunk_04_00.rs"),
        include_str!("chunk_04_01.rs"),
        include_str!("chunk_04_02.rs"),
        include_str!("chunk_04_03.rs"),
        include_str!("chunk_04_04.rs"),
        include_str!("chunk_05_00.rs"),
        include_str!("chunk_05_01.rs"),
        include_str!("chunk_05_02.rs"),
        include_str!("chunk_05_03.rs"),
        include_str!("chunk_06_00.rs"),
        include_str!("chunk_06_01.rs"),
        include_str!("chunk_06_02.rs"),
        include_str!("chunk_06_03.rs"),
        include_str!("chunk_06_04.rs"),
        include_str!("chunk_07_00.rs"),
        include_str!("chunk_07_01.rs"),
        include_str!("chunk_07_02.rs"),
        include_str!("chunk_07_03.rs"),
        include_str!("chunk_07_04.rs"),
        include_str!("chunk_08_00.rs"),
        include_str!("chunk_08_01.rs"),
        include_str!("chunk_08_02.rs"),
        include_str!("chunk_08_03.rs"),
        include_str!("chunk_08_04.rs"),
        include_str!("chunk_09_00.rs"),
        include_str!("chunk_09_01.rs"),
        include_str!("chunk_09_02.rs"),
        include_str!("chunk_09_03.rs"),
        include_str!("chunk_09_04.rs"),
        include_str!("chunk_10_00.rs"),
        include_str!("chunk_10_01.rs"),
        include_str!("chunk_10_02.rs"),
        include_str!("chunk_10_03.rs"),
        include_str!("chunk_10_04.rs"),
        include_str!("chunk_11_00.rs"),
        include_str!("chunk_11_01.rs"),
        include_str!("chunk_11_02.rs"),
        include_str!("chunk_11_03.rs"),
        include_str!("chunk_11_04.rs"),
        include_str!("chunk_12.rs"),
        include_str!("chunk_13.rs"),
    );
    let run_env = concat!("C2R_RUN_", "CLANG_AST_TESTS");
    let old_gate_message = concat!("set C2R_RUN_", "CLANG_AST_TESTS=1 to run");
    let windows_clang_default = concat!("C:/Program Files", "/LLVM/bin/clang.exe");
    let windows_llvm_prefix = concat!("C:/Program Files", "/LLVM");

    assert!(
        !source.contains(old_gate_message),
        "real clang tests must not early-return as successful tests when the opt-in env is unset"
    );
    assert!(
        !source.contains(windows_clang_default),
        "real clang tests must use the shared Linux-first clang resolver instead of a Windows fallback"
    );
    assert!(
        !source.contains(windows_llvm_prefix),
        "real clang tests must not carry hardcoded Windows LLVM host paths"
    );
    assert_eq!(
        source.matches(run_env).count(),
        1,
        "real clang opt-in env should be declared once in the shared helper"
    );
    assert_eq!(
        source
            .matches("#[ignore = \"requires real clang AST smoke test opt-in\"]")
            .count(),
        source
            .lines()
            .filter(|line| line.trim() == "let clang_path = real_clang_ast_test_setup();")
            .count(),
        "every real clang test calling the setup helper must be visibly ignored by default"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
const REAL_CLANG_AST_TEST_ENV: &str = "C2R_RUN_CLANG_AST_TESTS";

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn real_clang_ast_test_setup() -> PathBuf {
    if std::env::var(REAL_CLANG_AST_TEST_ENV).ok().as_deref() != Some("1") {
        panic!(
            "real clang AST smoke tests are ignored by default; rerun ignored tests with the opt-in env set to 1"
        );
    }

    let environment = std::env::vars_os()
        .filter_map(|(key, value)| {
            Some((
                key.into_string().ok()?,
                value
                    .into_string()
                    .unwrap_or_else(|value| value.to_string_lossy().into_owned()),
            ))
        })
        .collect::<std::collections::BTreeMap<_, _>>();
    let (clang_path, source) = resolve_clang_path(&environment).unwrap_or_else(|| {
        panic!(
            "real clang AST smoke tests require CLANG_PATH or a vendored clang under tools/llvm/bin or tools/clang/bin"
        )
    });
    assert!(
        clang_path.exists(),
        "resolved clang path from {source} does not exist: {}",
        clang_path.display()
    );
    clang_path
}

#[cfg(feature = "clang-lowering-report")]
struct EnvVarGuard {
    key: &'static str,
    original: Option<std::ffi::OsString>,
}

#[cfg(feature = "clang-lowering-report")]
impl EnvVarGuard {
    fn set_path(key: &'static str, value: &std::path::Path) -> Self {
        let original = std::env::var_os(key);
        std::env::set_var(key, value);
        Self { key, original }
    }
}

#[cfg(feature = "clang-lowering-report")]
impl Drop for EnvVarGuard {
    fn drop(&mut self) {
        if let Some(value) = &self.original {
            std::env::set_var(self.key, value);
        } else {
            std::env::remove_var(self.key);
        }
    }
}

#[cfg(feature = "typed-ir")]
fn assert_rust_snippet_compiles(name: &str, rust_code: &str) {
    let out_dir = unique_out_dir(name);
    fs::create_dir_all(&out_dir).unwrap();
    let source = out_dir.join("lib.rs");
    let output = out_dir.join("lib.rlib");
    fs::write(&source, rust_code).unwrap();

    let rustc = std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into());
    let result = Command::new(rustc)
        .arg("--crate-type")
        .arg("lib")
        .arg(&source)
        .arg("-o")
        .arg(&output)
        .output()
        .unwrap_or_else(|error| panic!("failed to run rustc: {error}"));

    assert!(
        result.status.success(),
        "rustc failed for {name}\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&result.stdout),
        String::from_utf8_lossy(&result.stderr)
    );
    fs::remove_dir_all(out_dir).unwrap();
}

#[cfg(feature = "typed-ir")]
fn assert_rust_snippet_runs(name: &str, rust_code: &str, main_body: &str) {
    assert_rust_snippet_runs_with_overflow_checks(name, rust_code, main_body, true);
}

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
    let ast: Value = serde_json::from_str(include_str!("../../fixtures/clang_ast/add_one_ast.json"))
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
        serde_json::from_str(include_str!("../../fixtures/clang_ast/direct_call_ast.json"))
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
        serde_json::from_str(include_str!("../../fixtures/clang_ast/call_expression_chain_ast.json"))
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
    let ast: Value = serde_json::from_str(include_str!("../../fixtures/clang_ast/abs_call_ast.json"))
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

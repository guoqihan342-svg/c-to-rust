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
        include_str!("chunk_00.rs"),
        include_str!("chunk_01.rs"),
        include_str!("chunk_02.rs"),
        include_str!("chunk_03.rs"),
        include_str!("chunk_04.rs"),
        include_str!("chunk_05.rs"),
        include_str!("chunk_06.rs"),
        include_str!("chunk_07.rs"),
        include_str!("chunk_08.rs"),
        include_str!("chunk_09.rs"),
        include_str!("chunk_10.rs"),
        include_str!("chunk_11.rs"),
        include_str!("chunk_12.rs"),
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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_strlen_model_with_target_abi_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/strlen_call_ast.json"))
            .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "name_len",
        Some(&target_abi),
    )
    .expect("lower strlen fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(IrExpr::Call {
            callee, args, ty, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected strlen return call, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(callee, "strlen");
    assert_eq!(args.len(), 1);
    assert_eq!(ty.spelled, "size_t");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit modeled strlen from fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn name_len(name: &[i8]) -> usize"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return name.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\");"
        ),
        "{rust}"
    );
    assert!(!rust.contains("strlen(name)"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-strlen", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_memset_statement_void_pointer_return_without_clang() {
    let ast: Value = serde_json::from_str(
        r#"
{
  "kind": "TranslationUnitDecl",
  "inner": [
    {
      "kind": "FunctionDecl",
      "name": "clear_prefix",
      "type": { "qualType": "void (uint8_t *, size_t)" },
      "inner": [
        {
          "kind": "ParmVarDecl",
          "name": "out",
          "type": { "qualType": "uint8_t *" }
        },
        {
          "kind": "ParmVarDecl",
          "name": "count",
          "type": { "qualType": "size_t" }
        },
        {
          "kind": "CompoundStmt",
          "inner": [
            {
              "kind": "CallExpr",
              "type": { "qualType": "void *" },
              "inner": [
                {
                  "kind": "ImplicitCastExpr",
                  "castKind": "FunctionToPointerDecay",
                  "type": { "qualType": "void *(*)(void *, int, size_t)" },
                  "inner": [
                    {
                      "kind": "DeclRefExpr",
                      "type": { "qualType": "void *(void *, int, size_t)" },
                      "referencedDecl": {
                        "kind": "FunctionDecl",
                        "name": "memset"
                      }
                    }
                  ]
                },
                {
                  "kind": "ImplicitCastExpr",
                  "castKind": "BitCast",
                  "type": { "qualType": "void *" },
                  "inner": [
                    {
                      "kind": "ImplicitCastExpr",
                      "castKind": "LValueToRValue",
                      "type": { "qualType": "uint8_t *" },
                      "inner": [
                        {
                          "kind": "DeclRefExpr",
                          "type": { "qualType": "uint8_t *" },
                          "referencedDecl": {
                            "kind": "ParmVarDecl",
                            "name": "out"
                          }
                        }
                      ]
                    }
                  ]
                },
                {
                  "kind": "IntegerLiteral",
                  "type": { "qualType": "int" },
                  "value": "0"
                },
                {
                  "kind": "ImplicitCastExpr",
                  "castKind": "LValueToRValue",
                  "type": { "qualType": "size_t" },
                  "inner": [
                    {
                      "kind": "DeclRefExpr",
                      "type": { "qualType": "size_t" },
                      "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "count"
                      }
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
"#,
    )
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "clear_prefix",
        Some(&target_abi),
    )
    .expect("lower clang memset statement fixture without invoking clang");
    let [IrStmt::Expr {
        expr: IrExpr::Call {
            callee, args, ty, ..
        },
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected memset expression statement, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(callee, "memset");
    assert_eq!(args.len(), 3);
    assert_eq!(ty.canonical, "void *");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit modeled memset statement from clang fixture typed IR");
    let rust = &emitted.rust;

    assert!(!rust.contains("memset(out, 0, count)"), "{rust}");
    assert!(
        rust.contains("pub fn clear_prefix(mut out: &mut [u8], count: usize)"),
        "{rust}"
    );
    assert!(rust.contains(".get_mut(..(count as usize))"), "{rust}");
    assert!(rust.contains(".fill(0u8);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-memset-void-pointer",
        rust,
        r#"
    let mut out = [1u8, 2, 3, 4];
    clear_prefix(&mut out, 3);
    assert_eq!(out, [0u8, 0, 0, 4]);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_memcpy_statement_void_pointer_return_without_clang() {
    let ast: Value = serde_json::from_str(
        r#"
{
  "kind": "TranslationUnitDecl",
  "inner": [
    {
      "kind": "FunctionDecl",
      "name": "copy_prefix",
      "type": { "qualType": "void (const uint8_t *restrict, uint8_t *restrict, size_t)" },
      "inner": [
        {
          "kind": "ParmVarDecl",
          "name": "src",
          "type": { "qualType": "const uint8_t *restrict" }
        },
        {
          "kind": "ParmVarDecl",
          "name": "out",
          "type": { "qualType": "uint8_t *restrict" }
        },
        {
          "kind": "ParmVarDecl",
          "name": "count",
          "type": { "qualType": "size_t" }
        },
        {
          "kind": "CompoundStmt",
          "inner": [
            {
              "kind": "CallExpr",
              "type": { "qualType": "void *" },
              "inner": [
                {
                  "kind": "ImplicitCastExpr",
                  "castKind": "FunctionToPointerDecay",
                  "type": { "qualType": "void *(*)(void *, const void *, size_t)" },
                  "inner": [
                    {
                      "kind": "DeclRefExpr",
                      "type": { "qualType": "void *(void *, const void *, size_t)" },
                      "referencedDecl": {
                        "kind": "FunctionDecl",
                        "name": "memcpy"
                      }
                    }
                  ]
                },
                {
                  "kind": "ImplicitCastExpr",
                  "castKind": "BitCast",
                  "type": { "qualType": "void *" },
                  "inner": [
                    {
                      "kind": "ImplicitCastExpr",
                      "castKind": "LValueToRValue",
                      "type": { "qualType": "uint8_t *restrict" },
                      "inner": [
                        {
                          "kind": "DeclRefExpr",
                          "type": { "qualType": "uint8_t *restrict" },
                          "referencedDecl": {
                            "kind": "ParmVarDecl",
                            "name": "out"
                          }
                        }
                      ]
                    }
                  ]
                },
                {
                  "kind": "ImplicitCastExpr",
                  "castKind": "BitCast",
                  "type": { "qualType": "const void *" },
                  "inner": [
                    {
                      "kind": "ImplicitCastExpr",
                      "castKind": "LValueToRValue",
                      "type": { "qualType": "const uint8_t *restrict" },
                      "inner": [
                        {
                          "kind": "DeclRefExpr",
                          "type": { "qualType": "const uint8_t *restrict" },
                          "referencedDecl": {
                            "kind": "ParmVarDecl",
                            "name": "src"
                          }
                        }
                      ]
                    }
                  ]
                },
                {
                  "kind": "ImplicitCastExpr",
                  "castKind": "LValueToRValue",
                  "type": { "qualType": "size_t" },
                  "inner": [
                    {
                      "kind": "DeclRefExpr",
                      "type": { "qualType": "size_t" },
                      "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "count"
                      }
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
"#,
    )
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "copy_prefix",
        Some(&target_abi),
    )
    .expect("lower clang memcpy statement fixture without invoking clang");
    let [IrStmt::Expr {
        expr: IrExpr::Call {
            callee, args, ty, ..
        },
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected memcpy expression statement, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(callee, "memcpy");
    assert_eq!(args.len(), 3);
    assert_eq!(ty.canonical, "void *");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit modeled memcpy statement from clang fixture typed IR");
    let rust = &emitted.rust;

    assert!(!rust.contains("memcpy(out, src, count)"), "{rust}");
    assert!(
        rust.contains("pub fn copy_prefix(src: &[u8], mut out: &mut [u8], count: usize)"),
        "{rust}"
    );
    assert!(rust.contains("copy_from_slice"), "{rust}");
    assert!(
        rust.contains("C memcpy source precondition violated"),
        "{rust}"
    );
    assert!(
        rust.contains("C memcpy destination precondition violated"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-memcpy-void-pointer",
        rust,
        r#"
    let src = [1u8, 2, 3, 4];
    let mut out = [0u8; 4];
    copy_prefix(&src, &mut out, 3);
    assert_eq!(out, [1u8, 2, 3, 0]);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_record_field_subset_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/record_field_ast.json"))
            .expect("fixture JSON");

    let point_x = lower_function_and_globals_from_clang_ast_json_value(&ast, "point_x")
        .expect("lower record value field read fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Member {
                field,
                is_arrow: false,
                ..
            }),
        ..
    }] = point_x.function_ir.body.as_slice()
    else {
        panic!(
            "expected record value field read return, got {:?}",
            point_x.function_ir.body
        );
    };
    assert_eq!(field, "x");
    let emitted = emit_rust_from_ir_with_globals(&point_x.function_ir, &point_x.globals)
        .expect("emit Rust from record value field read fixture");
    let rust = &emitted.rust;
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(rust.contains("pub fn point_x(p: Point) -> i32"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-record-value-read", rust);

    let set_point_x = lower_function_and_globals_from_clang_ast_json_value(&ast, "set_point_x")
        .expect("lower record value field assignment fixture without invoking clang");
    let [IrStmt::Assign { target, .. }, IrStmt::Return {
        value: Some(IrExpr::Member { field, .. }),
        ..
    }] = set_point_x.function_ir.body.as_slice()
    else {
        panic!(
            "expected record value field assignment and return, got {:?}",
            set_point_x.function_ir.body
        );
    };
    assert!(
        matches!(target, IrExpr::Member { field, is_arrow: false, .. } if field == "x"),
        "expected dot member assignment target, got {target:?}"
    );
    assert_eq!(field, "x");
    let emitted = emit_rust_from_ir_with_globals(&set_point_x.function_ir, &set_point_x.globals)
        .expect("emit Rust from record value field assignment fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn set_point_x(mut p: Point, value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-record-value-assignment", rust);

    let point_x_ptr = lower_function_and_globals_from_clang_ast_json_value(&ast, "point_x_ptr")
        .expect("lower readonly record pointer field read fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Member {
                field,
                is_arrow: true,
                ..
            }),
        ..
    }] = point_x_ptr.function_ir.body.as_slice()
    else {
        panic!(
            "expected readonly arrow member read return, got {:?}",
            point_x_ptr.function_ir.body
        );
    };
    assert_eq!(field, "x");
    let emitted = emit_rust_from_ir_with_globals(&point_x_ptr.function_ir, &point_x_ptr.globals)
        .expect("emit Rust from readonly record pointer field read fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn point_x_ptr(p: &Point) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return p.x;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-record-arrow-read", rust);

    let write_point_x = lower_function_and_globals_from_clang_ast_json_value(&ast, "write_point_x")
        .expect("lower mutable record pointer field write fixture without invoking clang");
    let [IrStmt::Assign { target, .. }] = write_point_x.function_ir.body.as_slice() else {
        panic!(
            "expected mutable arrow member assignment, got {:?}",
            write_point_x.function_ir.body
        );
    };
    assert!(
        matches!(target, IrExpr::Member { field, is_arrow: true, .. } if field == "x"),
        "expected arrow member assignment target, got {target:?}"
    );
    let emitted =
        emit_rust_from_ir_with_globals(&write_point_x.function_ir, &write_point_x.globals)
            .expect("emit Rust from mutable record pointer field write fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn write_point_x(mut p: &mut Point, value: i32)"),
        "{rust}"
    );
    assert!(rust.contains("p.x = value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-record-arrow-write", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_mutable_record_pointer_opaque_pointer_field_cast_write_without_clang()
{
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/record_pointer_field_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "make_blob",
        Some(&target_abi),
    )
    .expect("lower opaque pointer record field fixture without invoking clang");

    let [IrStmt::Assign {
        target: buf_target,
        value: buf_value,
        ..
    }, IrStmt::Assign {
        target: size_target,
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected two field assignments and identity return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert!(
        matches!(buf_target, IrExpr::Member { field, is_arrow: true, .. } if field == "buf"),
        "expected blob->buf assignment target, got {buf_target:?}"
    );
    assert!(
        matches!(size_target, IrExpr::Member { field, is_arrow: true, .. } if field == "size"),
        "expected blob->size assignment target, got {size_target:?}"
    );
    match buf_value {
        IrExpr::Cast {
            target,
            expr,
            implicit: false,
            ..
        } => {
            assert!(matches!(target.kind, IrTypeKind::Pointer { .. }));
            assert!(matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "value"));
        }
        other => panic!("expected opaque pointer cast RHS, got {other:?}"),
    }
    assert_eq!(return_name, "blob");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from opaque pointer record field fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Blob"), "{rust}");
    assert!(rust.contains("pub buf: *mut core::ffi::c_void"), "{rust}");
    assert!(rust.contains("pub size: usize"), "{rust}");
    assert!(
        rust.contains(
            "pub fn make_blob(mut blob: &mut Blob, value: *const core::ffi::c_void, len: usize) -> &mut Blob"
        ),
        "{rust}"
    );
    assert!(
        rust.contains("blob.buf = (value as *mut core::ffi::c_void);"),
        "{rust}"
    );
    assert!(rust.contains("blob.size = len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-record-opaque-pointer-field-cast",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_typedef_record_pointer_field_write_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/record_pointer_field_typedef_ast.json"
    ))
    .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "make_blob_typedef",
        Some(&target_abi),
    )
    .expect("lower typedef-backed record pointer field fixture without invoking clang");

    let [IrStmt::Assign {
        target: buf_target,
        value: buf_value,
        ..
    }, IrStmt::Assign {
        target: size_target,
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected two field assignments and identity return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert!(
        matches!(buf_target, IrExpr::Member { field, is_arrow: true, .. } if field == "buf"),
        "expected blob->buf assignment target, got {buf_target:?}"
    );
    assert!(
        matches!(size_target, IrExpr::Member { field, is_arrow: true, .. } if field == "size"),
        "expected blob->size assignment target, got {size_target:?}"
    );
    match buf_value {
        IrExpr::Cast {
            target,
            expr,
            implicit: false,
            ..
        } => {
            assert_eq!(target.canonical, "void *");
            assert!(matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "value"));
        }
        other => panic!("expected opaque pointer cast RHS, got {other:?}"),
    }
    assert_eq!(return_name, "blob");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from typedef-backed record pointer field fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("pub buf: *mut core::ffi::c_void"), "{rust}");
    assert!(rust.contains("pub size: usize"), "{rust}");
    assert!(
        rust.contains(
            "pub fn make_blob_typedef(mut blob: &mut FdbBlob, value: *const core::ffi::c_void, len: usize) -> &mut FdbBlob"
        ),
        "{rust}"
    );
    assert!(
        rust.contains("blob.buf = (value as *mut core::ffi::c_void);"),
        "{rust}"
    );
    assert!(rust.contains("blob.size = len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-typedef-record-pointer-field-cast",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_usual_arithmetic_integral_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/usual_arithmetic_ast.json"
    ))
    .expect("fixture JSON");

    let add_byte = lower_function_and_globals_from_clang_ast_json_value(&ast, "add_byte")
        .expect("lower clang-proven usual arithmetic fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary { rhs, ty, .. }),
        ..
    }] = add_byte.function_ir.body.as_slice()
    else {
        panic!(
            "expected usual arithmetic return binary, got {:?}",
            add_byte.function_ir.body
        );
    };
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    assert!(
        matches!(
            rhs.as_ref(),
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ),
        "expected clang-proven IntegralCast on RHS, got {rhs:?}"
    );
    let emitted = emit_rust_from_ir_with_globals(&add_byte.function_ir, &add_byte.globals)
        .expect("emit Rust from clang-proven usual arithmetic fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn add_byte(acc: u32, byte: u8) -> u32"),
        "{rust}"
    );
    assert!(
        rust.contains("return acc.wrapping_add((byte as u32));"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-usual-arithmetic-cast", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_unary_plus_integer_promotion_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/unary_integer_conversion_ast.json"
    ))
    .expect("fixture JSON");

    let promoted = lower_function_and_globals_from_clang_ast_json_value(&ast, "promote_plus")
        .expect("lower clang-proven unary plus integer promotion fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Cast {
                implicit: true,
                target,
                expr,
                ..
            }),
        ..
    }] = promoted.function_ir.body.as_slice()
    else {
        panic!(
            "expected unary plus return to preserve IntegralPromotion as an IR cast, got {:?}",
            promoted.function_ir.body
        );
    };
    assert!(matches!(
        target.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let IrExpr::LValueToRValue {
        target: read_ty,
        expr: read_expr,
        ..
    } = expr.as_ref()
    else {
        panic!("expected promoted unary plus operand to preserve LValueToRValue, got {expr:?}");
    };
    assert!(matches!(
        read_ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 8
        }
    ));
    let IrExpr::Var { name, ty, .. } = read_expr.as_ref() else {
        panic!("expected promoted unary plus read operand to be the original parameter, got {read_expr:?}");
    };
    assert_eq!(name, "value");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 8
        }
    ));

    let emitted = emit_rust_from_ir_with_globals(&promoted.function_ir, &promoted.globals)
        .expect("emit Rust from clang-proven unary plus integer promotion fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn promote_plus(value: i8) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return (value as i32);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-unary-plus-integer-promotion",
        rust,
        "assert_eq!(promote_plus(-7i8), -7i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_implicit_integer_noop_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/implicit_integer_noop_cast_ast.json"
    ))
    .expect("fixture JSON");

    let identity = lower_function_and_globals_from_clang_ast_json_value(&ast, "identity_noop")
        .expect("lower clang-proven implicit integer NoOp cast fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Cast {
                implicit: true,
                target,
                expr,
                ..
            }),
        ..
    }] = identity.function_ir.body.as_slice()
    else {
        panic!(
            "expected integer NoOp return to preserve an IR cast, got {:?}",
            identity.function_ir.body
        );
    };
    assert!(matches!(
        target.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let IrExpr::LValueToRValue {
        target: read_target,
        expr: read_expr,
        ..
    } = expr.as_ref()
    else {
        panic!("expected NoOp cast operand to be an explicit LValueToRValue read, got {expr:?}");
    };
    assert!(matches!(
        read_target.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let IrExpr::Var { name, ty, .. } = read_expr.as_ref() else {
        panic!("expected LValueToRValue operand to be the original parameter, got {read_expr:?}");
    };
    assert_eq!(name, "value");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));

    let emitted = emit_rust_from_ir_with_globals(&identity.function_ir, &identity.globals)
        .expect("emit Rust from clang-proven implicit integer NoOp cast fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn identity_noop(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return (value as i32);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-implicit-integer-noop-cast",
        rust,
        "assert_eq!(identity_noop(-7i32), -7i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_integer_lvalue_to_rvalue_return_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/lvalue_to_rvalue_integer_return_ast.json"
    ))
    .expect("fixture JSON");

    let read_value = lower_function_and_globals_from_clang_ast_json_value(&ast, "read_value")
        .expect("lower clang-proven integer LValueToRValue fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(expr), ..
    }] = read_value.function_ir.body.as_slice()
    else {
        panic!(
            "expected integer LValueToRValue return expression, got {:?}",
            read_value.function_ir.body
        );
    };
    let lowered_json = serde_json::to_value(expr).expect("serialize return expression");
    let Some(lvalue_to_rvalue) = lowered_json.get("LValueToRValue") else {
        panic!("expected explicit LValueToRValue IR node, got {lowered_json}");
    };
    assert_eq!(lvalue_to_rvalue["target"]["kind"]["Integer"]["width"], 32);
    assert_eq!(lvalue_to_rvalue["expr"]["Var"]["name"], "value");

    let emitted = emit_rust_from_ir_with_globals(&read_value.function_ir, &read_value.globals)
        .expect("emit Rust from clang-proven integer LValueToRValue fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn read_value(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return value;"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-integer-lvalue-to-rvalue",
        rust,
        "assert_eq!(read_value(-7i32), -7i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_usual_arithmetic_missing_integral_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/usual_arithmetic_ast.json"
    ))
    .expect("fixture JSON");
    let missing_cast =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "missing_integral_cast")
            .expect("lower malformed fixture without explicit usual arithmetic cast");
    let error = emit_rust_from_ir_with_globals(&missing_cast.function_ir, &missing_cast.globals)
        .expect_err("missing usual arithmetic cast must fail closed");
    assert!(
        error.reason.contains(
            "usual arithmetic conversion requires explicit IntegralCast/IntegralPromotion"
        ),
        "{}",
        error.reason
    );
    assert!(
        error
            .reason
            .contains("binary operand types must match result type for +"),
        "{}",
        error.reason
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_explicit_enum_constant_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let status_code = lower_function_and_globals_from_clang_ast_json_value(&ast, "status_code")
        .expect("lower explicit enum constant fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::LitInt {
                value,
                spelling,
                ty,
                ..
            }),
        ..
    }] = status_code.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum constant return literal, got {:?}",
            status_code.function_ir.body
        );
    };
    assert_eq!(*value, 7);
    assert_eq!(spelling, "7");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&status_code.function_ir, &status_code.globals)
        .expect("emit Rust from explicit enum constant fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn status_code() -> i32"), "{rust}");
    assert!(rust.contains("return 7i32;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-constant", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_enum_constant_in_binary_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let add_status = lower_function_and_globals_from_clang_ast_json_value(&ast, "add_status")
        .expect("lower explicit enum constant binary fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(IrExpr::Binary { rhs, ty, .. }),
        ..
    }] = add_status.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum constant binary return, got {:?}",
            add_status.function_ir.body
        );
    };
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt {
            value: 7,
            spelling,
            ..
        } if spelling == "7"
    ));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&add_status.function_ir, &add_status.globals)
        .expect("emit Rust from enum constant binary fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn add_status(value: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return value.checked_add(7i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-constant-binary", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_enum_constant_in_readonly_global_initializer_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_status_table")
        .expect("lower explicit enum constant global initializer fixture without invoking clang");
    assert_eq!(
        lowered
            .globals
            .iter()
            .find(|global| global.name == "status_table")
            .map(|global| &global.init),
        Some(&IrGlobalInit::IntegerArray(vec![7, 0]))
    );

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from enum constant global initializer fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("const STATUS_TABLE: [i32; 2] = [7i32, 0i32];"),
        "{rust}"
    );
    assert!(
        rust.contains("return STATUS_TABLE[0i32 as usize];"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-enum-constant-global-initializer",
        rust,
        r#"
    assert_eq!(lookup_status_table(), 7);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_implicit_enum_constant_in_readonly_global_initializer_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_pending_status_table")
            .expect("function shape should lower before unsupported enum global is emitted");
    assert!(
        lowered
            .globals
            .iter()
            .all(|global| global.name != "pending_status_table"),
        "implicit enum global initializer must not be collected"
    );

    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("referenced implicit enum global initializer must fail closed");
    assert!(
        error
            .reason
            .contains("index base pending_status_table is not declared"),
        "unexpected error: {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_enum_constant_without_explicit_value_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "implicit_status_code")
        .expect_err("implicit enum constant without explicit ConstantExpr must fail closed");
    assert_eq!(error.kind, "unsupported_clang_expr");
    assert!(
        error.message.contains("EnumConstantDecl STATUS_PENDING"),
        "{}",
        error.message
    );
    assert!(
        error.message.contains("explicit ConstantExpr value"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_keeps_enum_typed_function_unsupported_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let error = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "identity_status",
        Some(&target_abi),
    )
    .expect_err("enum-typed functions remain unsupported");
    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error.message.contains("EnumConstantDecl STATUS_PENDING"),
        "{}",
        error.message
    );
    assert!(
        error.message.contains("explicit ConstantExpr value"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_explicit_enum_typed_identity_without_target_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "identity_mode")
        .expect_err("enum-typed scalar lowering requires target ABI profile");
    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(error.message.contains("enum mode"), "{}", error.message);
    assert!(
        error.message.contains("target ABI profile evidence"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_named_enum_without_complete_definition_flag() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x3100",
                "kind": "EnumDecl",
                "name": "mode",
                "inner": [
                    {
                        "id": "0x3101",
                        "kind": "EnumConstantDecl",
                        "name": "MODE_OK",
                        "type": { "qualType": "int" },
                        "inner": [
                            {
                                "kind": "ConstantExpr",
                                "type": { "qualType": "int" },
                                "value": "0",
                                "inner": [
                                    {
                                        "kind": "IntegerLiteral",
                                        "type": { "qualType": "int" },
                                        "value": "0"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "identity_mode",
                "type": { "qualType": "enum mode (enum mode)" },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "value",
                        "type": { "qualType": "enum mode" }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "LValueToRValue",
                                        "type": { "qualType": "enum mode" },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "enum mode" },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "value"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    });
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let error = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "identity_mode",
        Some(&target_abi),
    )
    .expect_err("named enum without completeDefinition must fail closed");

    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error
            .message
            .contains("EnumDecl mode is not a complete definition"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_explicit_i32_enum_typed_identity_with_target_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "identity_mode",
        Some(&target_abi),
    )
    .expect("lower explicit i32 enum-typed identity fixture without invoking clang");
    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lowered.function_ir.params.as_slice(),
        [IrParam {
            name,
            ty:
                IrType {
                    kind:
                        IrTypeKind::Integer {
                            signed: true,
                            width: 32
                        },
                    ..
                },
            ..
        }] if name == "value"
    ));
    let [IrStmt::Return {
        value: Some(IrExpr::Var { name, ty, .. }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum typed identity return variable, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(name, "value");
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from explicit i32 enum-typed identity fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn identity_mode(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return value;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-typed-identity", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_anonymous_typedef_enum_alias_with_target_abi() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x2000",
                "kind": "EnumDecl",
                "completeDefinition": true,
                "inner": [
                    {
                        "id": "0x2001",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_NO_ERR",
                        "type": { "qualType": "int" },
                        "inner": [
                            {
                                "kind": "ConstantExpr",
                                "type": { "qualType": "int" },
                                "value": "0",
                                "inner": [
                                    {
                                        "kind": "IntegerLiteral",
                                        "type": { "qualType": "int" },
                                        "value": "0"
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "id": "0x2002",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_INIT_FAILED",
                        "type": { "qualType": "int" },
                        "inner": [
                            {
                                "kind": "ConstantExpr",
                                "type": { "qualType": "int" },
                                "value": "7",
                                "inner": [
                                    {
                                        "kind": "IntegerLiteral",
                                        "type": { "qualType": "int" },
                                        "value": "7"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": { "qualType": "enum fdb_err_t" },
                "inner": [
                    {
                        "kind": "EnumType",
                        "type": { "qualType": "enum fdb_err_t" },
                        "decl": {
                            "id": "0x2000",
                            "kind": "EnumDecl",
                            "name": ""
                        },
                        "isTagOwned": true
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "id_err",
                "type": {
                    "qualType": "fdb_err_t (fdb_err_t)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "e",
                        "type": {
                            "qualType": "fdb_err_t",
                            "desugaredQualType": "enum fdb_err_t"
                        }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "LValueToRValue",
                                        "type": {
                                            "qualType": "fdb_err_t",
                                            "desugaredQualType": "enum fdb_err_t"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t"
                                                },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "e"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    });
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "id_err",
        Some(&target_abi),
    )
    .expect("lower anonymous typedef enum alias identity fixture without invoking clang");
    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lowered.function_ir.params.as_slice(),
        [IrParam {
            name,
            ty:
                IrType {
                    kind:
                        IrTypeKind::Integer {
                            signed: true,
                            width: 32
                        },
                    ..
                },
            ..
        }] if name == "e"
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from anonymous typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-typedef-enum-alias", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_owned_typedef_enum_alias_without_complete_definition_flag() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x3000",
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": { "qualType": "enum fdb_err_t" },
                "inner": [
                    {
                        "id": "0x3001",
                        "kind": "EnumDecl",
                        "inner": [
                            {
                                "id": "0x3002",
                                "kind": "EnumConstantDecl",
                                "name": "FDB_NO_ERR",
                                "type": { "qualType": "int" },
                                "inner": [
                                    {
                                        "kind": "ConstantExpr",
                                        "type": { "qualType": "int" },
                                        "value": "0",
                                        "inner": [
                                            {
                                                "kind": "IntegerLiteral",
                                                "type": { "qualType": "int" },
                                                "value": "0"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "id": "0x3003",
                                "kind": "EnumConstantDecl",
                                "name": "FDB_INIT_FAILED",
                                "type": { "qualType": "int" },
                                "inner": [
                                    {
                                        "kind": "ConstantExpr",
                                        "type": { "qualType": "int" },
                                        "value": "7",
                                        "inner": [
                                            {
                                                "kind": "IntegerLiteral",
                                                "type": { "qualType": "int" },
                                                "value": "7"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "id_err",
                "type": {
                    "qualType": "fdb_err_t (fdb_err_t)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "e",
                        "type": {
                            "qualType": "fdb_err_t",
                            "desugaredQualType": "enum fdb_err_t",
                            "typeAliasDeclId": "0x3000"
                        }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "LValueToRValue",
                                        "type": {
                                            "qualType": "fdb_err_t",
                                            "desugaredQualType": "enum fdb_err_t",
                                            "typeAliasDeclId": "0x3000"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t",
                                                    "typeAliasDeclId": "0x3000"
                                                },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "e"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    });
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "id_err",
        Some(&target_abi),
    )
    .expect("lower FlashDB-style owned typedef enum alias without completeDefinition flag");

    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lowered.function_ir.params.as_slice(),
        [IrParam {
            name,
            ty:
                IrType {
                    kind:
                        IrTypeKind::Integer {
                            signed: true,
                            width: 32
                        },
                    ..
                },
            ..
        }] if name == "e"
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from FlashDB-style owned typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-owned-typedef-enum-alias", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_typedef_enum_alias_reference_with_implicit_values() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x3201",
                "kind": "EnumDecl",
                "inner": [
                    {
                        "id": "0x3202",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_NO_ERR",
                        "type": { "qualType": "int" }
                    },
                    {
                        "id": "0x3203",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_INIT_FAILED",
                        "type": { "qualType": "int" }
                    }
                ]
            },
            {
                "id": "0x3200",
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": { "qualType": "enum fdb_err_t" },
                "inner": [
                    {
                        "kind": "EnumType",
                        "type": { "qualType": "enum fdb_err_t" },
                        "decl": {
                            "kind": "EnumDecl",
                            "id": "0x3201"
                        }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "id_err",
                "type": {
                    "qualType": "fdb_err_t (fdb_err_t)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "e",
                        "type": {
                            "qualType": "fdb_err_t",
                            "desugaredQualType": "enum fdb_err_t",
                            "typeAliasDeclId": "0x3200"
                        }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "LValueToRValue",
                                        "type": {
                                            "qualType": "fdb_err_t",
                                            "desugaredQualType": "enum fdb_err_t",
                                            "typeAliasDeclId": "0x3200"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t",
                                                    "typeAliasDeclId": "0x3200"
                                                },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "e"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    });
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "id_err",
        Some(&target_abi),
    )
    .expect("lower FlashDB-style typedef enum alias reference with implicit values");

    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from FlashDB-style implicit typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-typedef-enum-alias-implicit-values",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_enum_local_variable_branch_and_assignment_with_target_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "choose_mode",
        Some(&target_abi),
    )
    .expect("lower explicit i32 enum local variable fixture without invoking clang");
    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lowered.function_ir.params.as_slice(),
        [IrParam {
            name,
            ty:
                IrType {
                    kind:
                        IrTypeKind::Integer {
                            signed: true,
                            width: 32
                        },
                    ..
                },
            ..
        }] if name == "value"
    ));
    let [IrStmt::Decl {
        name: decl_name,
        ty: decl_ty,
        init: Some(IrExpr::LitInt { value: 1, .. }),
        ..
    }, IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum local declaration, branch assignment, and return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(decl_name, "current");
    assert!(matches!(
        decl_ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::Eq,
            lhs,
            rhs,
            ..
        } if matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "value")
            && matches!(rhs.as_ref(), IrExpr::LitInt { value: 2, .. })
    ));
    assert!(else_body.is_empty());
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign {
            target: IrExpr::Var { name: target_name, .. },
            value: IrExpr::LitInt { value: 2, .. },
            ..
        }] if target_name == "current"
    ));
    assert_eq!(return_name, "current");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from explicit i32 enum local variable fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn choose_mode(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let mut current: i32 = 1i32;"), "{rust}");
    assert!(rust.contains("if (value == 2i32)"), "{rust}");
    assert!(rust.contains("current = 2i32;"), "{rust}");
    assert!(rust.contains("return current;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-local-variable", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_sizeof_enum_without_layout_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let error = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "sizeof_mode_bytes",
        Some(&target_abi),
    )
    .expect_err("sizeof(enum) still needs explicit enum layout/ABI proof");
    assert_eq!(error.kind, "unsupported_sizeof_type");
    assert!(
        error.message.contains("sizeof(enum mode)"),
        "{}",
        error.message
    );
    assert!(
        error
            .message
            .contains("requires explicit C layout/ABI provenance"),
        "{}",
        error.message
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_pointer_value_call_and_return_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/pointer_value_boundary_ast.json"
    ))
    .expect("fixture JSON");

    let lowered_call = lower_function_and_globals_from_clang_ast_json_value(&ast, "call_take_ptr")
        .expect("lower pointer value call fixture without invoking clang");
    let call_error =
        emit_rust_from_ir_with_globals(&lowered_call.function_ir, &lowered_call.globals)
            .expect_err("pointer value call arg must fail closed");
    assert!(
        call_error
            .reason
            .contains("call arg[0] pointer value argument"),
        "{:?}",
        call_error.reason
    );
    assert!(
        call_error.reason.contains("const int *"),
        "{:?}",
        call_error.reason
    );

    let lowered_return =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "return_pointer")
            .expect("lower pointer value return fixture without invoking clang");
    let return_error =
        emit_rust_from_ir_with_globals(&lowered_return.function_ir, &lowered_return.globals)
            .expect_err("pointer value return must fail closed");
    assert!(
        return_error.reason.contains("pointer value return"),
        "{:?}",
        return_error.reason
    );
    assert!(
        return_error.reason.contains("const int *"),
        "{:?}",
        return_error.reason
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_function_name_decay_argument_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/function_decay_boundary_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "call_with_function_value")
            .expect("function-to-pointer decay argument should stay visible in typed IR");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust for bounded function name decay argument");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn call_with_function_value(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return apply(helper, value);"), "{rust}");
    let rust_with_helpers = format!(
        "fn helper(value: i32) -> i32 {{ value + 1 }}\nfn apply(func: fn(i32) -> i32, value: i32) -> i32 {{ func(value) }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-function-name-decay-argument",
        &rust_with_helpers,
        "assert_eq!(call_with_function_value(41i32), 42i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_function_pointer_parameter_call_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/function_pointer_call_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "call_fn")
        .expect("lower function pointer parameter call fixture without invoking clang");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust for bounded function pointer parameter call");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn call_fn(fp: fn(i32) -> i32, value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return fp(value);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-function-pointer-param-call",
        rust,
        "fn inc(value: i32) -> i32 { value + 1 }\nassert_eq!(call_fn(inc, 41i32), 42i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_function_to_pointer_decay_without_lowering_evidence() {
    let i32_ty = ir_i32();
    let function_ty = ir_function_type("int (int)");
    let function_pointer_ty =
        ir_pointer("int (*)(int)", "int (*)(int)", function_ty.clone(), false);
    let decay_expr: IrExpr = serde_json::from_value(serde_json::json!({
        "FunctionToPointerDecay": {
            "target": serde_json::to_value(&function_pointer_ty).unwrap(),
            "expr": serde_json::to_value(ir_var("helper", function_ty)).unwrap(),
            "source_span": null
        }
    }))
    .expect("deserialize explicit function-to-pointer decay IR node");
    let ir = IrFunction {
        name: "bad_function_decay_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Expr {
                expr: decay_expr,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("function-to-pointer decay must stay fail closed");
    assert!(error.reason.contains("function-to-pointer decay"));
    assert!(error.reason.contains("function pointer value"));
    assert!(error.reason.contains("explicit function-pointer lowering"));
}

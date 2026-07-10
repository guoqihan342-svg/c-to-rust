#![cfg(all(feature = "clang-frontend", feature = "typed-ir"))]

use std::{
    fs,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

use c2r_translator::{
    clang_frontend::{
        lower_function_and_globals_from_clang_ast_json_value,
        lower_function_and_globals_from_clang_ast_json_value_with_target_abi,
    },
    typed_ir::{emit_rust_from_ir_with_globals, IrExpr, IrStmt, IrTypeKind},
    TargetAbiProfile,
};
use serde_json::{json, Value};

fn integer_to_bool_ast(
    function_name: &str,
    parameter_name: &str,
    parameter_type: &str,
    return_type: &str,
    explicit: bool,
) -> Value {
    let bool_conversion = json!({
        "kind": if explicit { "CStyleCastExpr" } else { "ImplicitCastExpr" },
        "castKind": "IntegralToBoolean",
        "type": { "qualType": "_Bool" },
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": parameter_type },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": parameter_type },
                "referencedDecl": {
                    "kind": "ParmVarDecl",
                    "name": parameter_name,
                    "type": { "qualType": parameter_type }
                }
            }]
        }]
    });
    let returned_value = if return_type == "_Bool" {
        bool_conversion
    } else {
        json!({
            "kind": "ImplicitCastExpr",
            "castKind": "IntegralCast",
            "type": { "qualType": return_type },
            "inner": [bool_conversion]
        })
    };

    json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "FunctionDecl",
            "name": function_name,
            "type": { "qualType": format!("{return_type} ({parameter_type})") },
            "inner": [
                {
                    "kind": "ParmVarDecl",
                    "name": parameter_name,
                    "type": { "qualType": parameter_type }
                },
                {
                    "kind": "CompoundStmt",
                    "inner": [{
                        "kind": "ReturnStmt",
                        "inner": [returned_value]
                    }]
                }
            ]
        }]
    })
}

fn lp64_abi() -> TargetAbiProfile {
    TargetAbiProfile {
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
    }
}

fn assert_rust_runs(name: &str, rust: &str, assertions: &str) {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let out_dir = std::env::temp_dir().join(format!("c2r-{name}-{nonce}"));
    fs::create_dir_all(&out_dir).expect("create rustc temp dir");
    let source = out_dir.join("main.rs");
    let binary = out_dir.join(if cfg!(windows) { "main.exe" } else { "main" });
    fs::write(&source, format!("{rust}\nfn main() {{\n{assertions}\n}}\n"))
        .expect("write emitted Rust");
    let compile = Command::new("rustc")
        .arg("--edition=2021")
        .arg(&source)
        .arg("-o")
        .arg(&binary)
        .output()
        .expect("run rustc");
    assert!(
        compile.status.success(),
        "rustc failed:\n{}\nsource:\n{}",
        String::from_utf8_lossy(&compile.stderr),
        fs::read_to_string(&source).expect("read failed source")
    );
    let run = Command::new(&binary).output().expect("run emitted Rust");
    assert!(
        run.status.success(),
        "emitted Rust failed:\n{}",
        String::from_utf8_lossy(&run.stderr)
    );
    let _ = fs::remove_dir_all(out_dir);
}

#[test]
fn implicit_integer_to_bool_variable_lowers_without_clang() {
    let ast = integer_to_bool_ast("normalize_flag", "source_value", "int", "_Bool", false);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "normalize_flag")
        .expect("lower clang-proven IntegralToBoolean variable conversion");

    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Conditional { ty, .. }),
            ..
        }] if matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 8
            }
        )
    ));
}

#[test]
fn renamed_explicit_integer_to_bool_uses_abi_and_runs_without_clang() {
    let ast = integer_to_bool_ast(
        "classify_payload",
        "payload_word",
        "unsigned long",
        "unsigned long",
        true,
    );
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "classify_payload",
        Some(&lp64_abi()),
    )
    .expect("lower renamed ABI-bound IntegralToBoolean conversion");
    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Cast { target, expr, .. }),
            ..
        }] if matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        ) && matches!(
            expr.as_ref(),
            IrExpr::Conditional { ty, .. } if matches!(
                ty.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 8
                }
            )
        )
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed integer truthiness normalization")
        .rust;

    assert!(
        emitted.contains("pub fn classify_payload(payload_word: u64) -> u64"),
        "{emitted}"
    );
    assert_rust_runs(
        "renamed-integer-to-bool",
        &emitted,
        "    assert_eq!(classify_payload(0), 0);\n    assert_eq!(classify_payload(256), 1);\n    assert_eq!(classify_payload(u64::MAX), 1);",
    );
}

#[test]
fn integer_to_bool_rejects_target_dependent_source_without_abi() {
    let ast = integer_to_bool_ast(
        "classify_payload",
        "payload_word",
        "unsigned long",
        "unsigned long",
        true,
    );

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "classify_payload")
        .expect_err("unsigned long conversion must require ABI width provenance");

    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error
            .message
            .contains("unsigned long requires target ABI width provenance"),
        "{error:?}"
    );
}

#[test]
fn pointer_to_bool_remains_fail_closed() {
    let ast = json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "FunctionDecl",
            "name": "pointer_state",
            "type": { "qualType": "_Bool (int *)" },
            "inner": [
                {
                    "kind": "ParmVarDecl",
                    "name": "candidate_ptr",
                    "type": { "qualType": "int *" }
                },
                {
                    "kind": "CompoundStmt",
                    "inner": [{
                        "kind": "ReturnStmt",
                        "inner": [{
                            "kind": "ImplicitCastExpr",
                            "castKind": "PointerToBoolean",
                            "type": { "qualType": "_Bool" },
                            "inner": [{
                                "kind": "ImplicitCastExpr",
                                "castKind": "LValueToRValue",
                                "type": { "qualType": "int *" },
                                "inner": [{
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int *" },
                                    "referencedDecl": {
                                        "kind": "ParmVarDecl",
                                        "name": "candidate_ptr"
                                    }
                                }]
                            }]
                        }]
                    }]
                }
            ]
        }]
    });

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "pointer_state")
        .expect_err("PointerToBoolean requires separate pointer semantics");

    assert_eq!(error.kind, "unsupported_clang_expr");
    assert!(error.message.contains("PointerToBoolean"), "{error:?}");
}

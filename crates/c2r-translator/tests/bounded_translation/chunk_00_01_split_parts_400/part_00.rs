#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_strlen_model_with_target_abi_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../../fixtures/clang_ast/strlen_call_ast.json"))
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
fn clang_ast_fixture_replays_strnlen_model_with_target_abi_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../../fixtures/clang_ast/strnlen_call_ast.json"))
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
        "bounded_name_len",
        Some(&target_abi),
    )
    .expect("lower strnlen fixture without invoking clang");
    let [IrStmt::Return {
        value: Some(IrExpr::Call {
            callee, args, ty, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected strnlen return call, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(callee, "strnlen");
    assert_eq!(args.len(), 2);
    assert_eq!(ty.spelled, "size_t");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit modeled strnlen from fixture typed IR");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn bounded_name_len(name: &[i8], max: usize) -> usize"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "let bytes = name.get(..(max as usize)).expect(\"C strnlen precondition violated\");"
        ),
        "{rust}"
    );
    assert!(rust.contains("bytes.iter().position(|&byte| byte == 0).unwrap_or(bytes.len())"), "{rust}");
    assert!(!rust.contains("strnlen(name, max)"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-strnlen", rust);
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

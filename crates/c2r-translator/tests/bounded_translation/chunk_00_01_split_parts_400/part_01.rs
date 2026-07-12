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

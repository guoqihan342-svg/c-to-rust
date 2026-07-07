#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_value_with_readonly_pointer_deref_operand() {
    let i32_ty = ir_i32();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ir = IrFunction {
        name: "first_is_zero_not".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(
                ir_deref(ir_var("p", const_u8_ptr_ty), u8_ty),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not deref value");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_is_zero_not(p: &[u8]) -> i32"));
    assert!(rust.contains("if p[0usize] == 0u8 { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-logical-not-deref-value", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_logical_not_value_with_readonly_pointer_add_index_deref_operand() {
    let i32_ty = ir_i32();
    let usize_ty = ir_usize();
    let u8_ty = ir_u8();
    let const_u8_ty = ir_const(u8_ty.clone());
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", const_u8_ty, false);
    let ptr_plus_index = ir_binary(
        IrBinOp::Add,
        ir_var("p", const_u8_ptr_ty.clone()),
        ir_var("i", usize_ty.clone()),
        const_u8_ptr_ty.clone(),
    );
    let ir = IrFunction {
        name: "offset_is_zero_not".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr_ty,
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty,
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_deref(ptr_plus_index, u8_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit logical not offset deref value");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn offset_is_zero_not(p: &[u8], i: usize) -> i32"));
    assert!(rust.contains("if p[i as usize] == 0u8 { 1i32 } else { 0i32 }"));
    assert_rust_snippet_compiles("typed-ir-logical-not-offset-deref-value", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_pointer_operand() {
    let i32_ty = ir_i32();
    let ptr_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_logical_not_pointer".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("ptr", ptr_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not pointer operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("logical not operand zero"));
    assert!(error.reason.contains("pointer type int * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_unsupported_operand_type() {
    let i32_ty = ir_i32();
    let unsupported_ty = IrType {
        spelled: "float".to_string(),
        canonical: "float".to_string(),
        kind: IrTypeKind::Unsupported {
            reason: "floating type is outside typed IR subset".to_string(),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_logical_not_float".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", unsupported_ty), i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("logical not unsupported operand type must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("logical not operand zero"));
    assert!(error
        .reason
        .contains("unsupported type float: floating type is outside typed IR subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_logical_not_value_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_logical_not_result_type".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_not(ir_var("value", i32_ty), u32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("logical not result type must be C int");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error
        .reason
        .contains("logical not result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_non_void_function_without_return_value_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "missing_return".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Expr {
            expr: ir_lit(1, "1", i32_ty),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-void function must return");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("non-void function must end with a return value"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_accepts_final_if_when_both_branches_return_values() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "return_from_if_else".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::If {
            condition: ir_var("flag", i32_ty.clone()),
            then_body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            }],
            else_body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "other".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("final if with returning branches should satisfy return gate");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn return_from_if_else(flag: i32, value: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("return helper(value);"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("return other(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-final-if-both-branches-return",
        &format!(
            "fn helper(value: i32) -> i32 {{ value + 1 }}\nfn other(value: i32) -> i32 {{ value - 1 }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_uninitialized_local_decl_assigned_before_read() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "assign_after_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("tmp", u32_ty.clone()),
                value: ir_lit(7, "7", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit assigned uninitialized local declaration");
    let rust = &emitted.rust;

    assert!(rust.contains("let mut tmp: u32;"), "{rust}");
    assert!(rust.contains("tmp = 7u32;"), "{rust}");
    assert!(rust.contains("return tmp;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-uninitialized-local-assigned-before-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_uninitialized_local_decl_read_before_assignment() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_uninit_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("uninitialized local read before assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("tmp"), "{:?}", error);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_rust_keyword_identifier_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "type".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("rust keyword function name must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("function identifier \"type\" is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_underscore_identifier_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "_".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("underscore function name must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("function identifier \"_\" is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_undeclared_var_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_var".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_var("x", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("undeclared var must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("var x is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_assign_to_undeclared_var_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_assign_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Assign {
                target: ir_var("x", i32_ty.clone()),
                value: ir_lit(1, "1", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(1, "1", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("undeclared assign target must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("assign target x is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_out_of_range_integer_literal_in_generic_emitter() {
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "bad_literal".to_string(),
        return_type: u8_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(256, "256", u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("out-of-range literal must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("literal value 256 does not fit type u8"));
}

#[test]
fn slice_spec_deserializes_real_tu_metadata_without_changing_translation() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/project",
        "source_file": "src/add_one.c",
        "source_files": [
            {
                "path": "src/add_one.c",
                "role": "source",
                "sha256": "source-file-sha"
            }
        ],
        "source_file_hashes": {
            "src/add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/add_one.c",
            "line_start": 10,
            "line_end": 12,
            "byte_start": 100,
            "byte_end": 160,
            "sha256": "function-span-sha"
        },
        "compile_commands": "build/compile_commands.json",
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "compile_commands.json",
            "clang_available": true
        }
    }))
    .unwrap();

    assert_eq!(spec.source_root.as_deref(), Some("C:/src/project"));
    assert_eq!(spec.source_file.as_deref(), Some("src/add_one.c"));
    assert_eq!(spec.source_files[0].path, "src/add_one.c");
    assert_eq!(
        spec.source_file_hashes
            .get("src/add_one.c")
            .map(String::as_str),
        Some("source-file-sha")
    );
    assert_eq!(
        spec.function_source_span
            .as_ref()
            .map(|span| span.sha256.as_str()),
        Some("function-span-sha")
    );
    assert_eq!(
        spec.compile_commands.as_deref(),
        Some("build/compile_commands.json")
    );

    let out_dir = unique_out_dir("real-tu-metadata");

    write_translation_artifacts(&spec, &out_dir).unwrap();

    let plan = json_file(out_dir.join("l3-add-one-auto-translation-plan.json"));
    let plan_errors = plan["errors"].as_array().expect("plan errors");
    assert!(
        plan_errors.iter().all(|error| {
            let kind = error["kind"].as_str().unwrap_or_default();
            kind.starts_with("legacy_") && kind.ends_with("_retired")
        }),
        "expected only retired-legacy diagnostics, got {plan_errors:?}"
    );
    let rust_draft = fs::read_to_string(out_dir.join("l3-add-one-rust-draft.rs")).unwrap();
    assert!(
        rust_draft.contains("pub fn add_one(value: i32) -> i32"),
        "{rust_draft}"
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_dry_run_uses_real_tu_metadata_without_libclang() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_files": [
            {
                "path": "src/fdb_utils.c",
                "role": "source",
                "sha256": "source-file-sha"
            }
        ],
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc", "tests"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let dry_run = parse_spec.dry_run();

    assert_eq!(parse_spec.source_root, PathBuf::from("C:/src/FlashDB"));
    assert_eq!(parse_spec.source_file, PathBuf::from("src/fdb_utils.c"));
    assert_eq!(parse_spec.function_name, "fdb_calc_crc32");
    assert_eq!(
        parse_spec.source_file_hashes["src/fdb_utils.c"],
        "source-file-sha"
    );
    assert_eq!(
        parse_spec
            .function_source_span
            .as_ref()
            .map(|span| span.sha256.as_str()),
        Some("function-span-sha")
    );
    assert!(parse_spec.compile_commands.is_none());
    assert_eq!(dry_run.status, "diagnostic_only");
    assert_eq!(dry_run.claim_boundary.role, "diagnostic_only");
    assert_eq!(dry_run.active_frontend.kind, "clang_ast_dump_json");
    assert_eq!(
        dry_run.active_frontend.command,
        "clang -Xclang -ast-dump=json -fsyntax-only"
    );
    assert_eq!(dry_run.active_frontend.required_env, vec!["CLANG_PATH"]);
    assert!(!dry_run.active_frontend.uses_libclang);
    assert_eq!(
        dry_run.arguments,
        vec![
            "-IC:/src/FlashDB/inc".to_string(),
            "-IC:/src/FlashDB/tests".to_string(),
            "-DFDB_USING_FILE_POSIX_MODE".to_string(),
        ]
    );
    assert!(dry_run
        .diagnostics
        .contains(&"LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH".to_string()));
}

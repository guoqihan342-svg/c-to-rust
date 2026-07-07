#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_report_records_unavailable_without_clang_path() {
    let environment = std::collections::BTreeMap::new();

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &PathBuf::from("add_one.c"),
        "add_one",
    );

    assert_eq!(report.status, "unavailable");
    assert_eq!(report.frontend, "clang");
    assert_eq!(report.function_name, "add_one");
    assert_eq!(report.source_file.as_deref(), Some("add_one.c"));
    assert_eq!(report.clang_path.as_deref(), None);
    assert!(report.function_ir.is_none());
    assert!(report
        .errors
        .iter()
        .any(|error| error.kind == "missing_clang_path"));
    assert!(report
        .diagnostics
        .iter()
        .any(|diagnostic| diagnostic.contains("CLANG_PATH is not set")));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_report_maps_unsupported_skeleton_without_ir() {
    let unsupported_type = ClangTypeSkeleton {
        spelled: "long double".to_string(),
        canonical: "long double".to_string(),
        kind: ClangTypeKind::Unsupported {
            reason: "long double is outside the current type skeleton".to_string(),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "unsupported_value".to_string(),
        return_type: unsupported_type.clone(),
        params: vec![],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: unsupported_type,
            }),
        }],
    };
    let environment = std::collections::BTreeMap::new();

    let report = lower_function_skeleton_report(&skeleton, &environment);

    assert_eq!(report.status, "unsupported");
    assert_eq!(report.frontend, "clang");
    assert_eq!(report.function_name, "unsupported_value");
    assert!(report.function_ir.is_none());
    assert!(report
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_clang_type"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-add-one");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("add_one.c");
    fs::write(
        &source_file,
        "int add_one(int value) { return value + 1; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "add_one")
        .expect("lower real clang AST add_one");
    let environment = std::collections::BTreeMap::from([
        (
            "CLANG_PATH".to_string(),
            clang_path.to_string_lossy().into_owned(),
        ),
        (
            "LIBCLANG_PATH".to_string(),
            "tools/llvm/bin/libclang.so".to_string(),
        ),
    ]);
    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_one");

    assert_eq!(ir.name, "add_one");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Binary {
                op: IrBinOp::Add,
                ..
            }),
            ..
        }]
    ));
    assert_eq!(report.status, "lowered");
    assert_eq!(report.frontend, "clang");
    assert!(report.errors.is_empty(), "{:?}", report.errors);
    assert_eq!(
        report
            .function_ir
            .as_ref()
            .map(|function| function.name.as_str()),
        Some("add_one")
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_real_scalar_subtraction_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-sub-one");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("sub_one.c");
    fs::write(
        &source_file,
        "int sub_one(int value) { return value - 1; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "sub_one")
        .expect("lower real clang AST sub_one");

    assert_eq!(ir.name, "sub_one");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Binary {
                op: IrBinOp::Sub,
                ..
            }),
            ..
        }]
    ));

    let emitted = emit_rust_from_ir(&ir).expect("emit real clang sub_one from typed IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(
        rust.contains("return value.checked_sub(1i32).expect(\"signed subtraction overflow\");")
    );
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-scalar-subtraction", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_real_scalar_mul_div_mod_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-mul-div-mod");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("mul_div_mod.c");
    fs::write(
        &source_file,
        "int mul_div_mod(int value) { return ((value * 3) / 2) % 5; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "mul_div_mod")
        .expect("lower real clang AST mul_div_mod");

    assert_eq!(ir.name, "mul_div_mod");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Binary {
                op: IrBinOp::Mod,
                ..
            }),
            ..
        }]
    ));

    let emitted = emit_rust_from_ir(&ir).expect("emit real clang mul_div_mod from typed IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn mul_div_mod(value: i32) -> i32"));
    assert!(rust.contains("return value.checked_mul(3i32).expect(\"signed multiplication overflow\").checked_div(2i32).expect(\"division by zero or signed overflow\").checked_rem(5i32).expect(\"modulo by zero or signed overflow\");"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-scalar-mul-div-mod", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_real_signed_unary_minus_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-neg-value");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("neg_value.c");
    fs::write(
        &source_file,
        "int neg_value(int value) { return -value; }\n",
    )
    .unwrap();

    let ir = lower_function_from_clang_ast_dump(&clang_path, &source_file, "neg_value")
        .expect("lower real clang AST neg_value");

    assert_eq!(ir.name, "neg_value");
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    assert!(matches!(
        ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::Unary {
                op: IrUnOp::Neg,
                ..
            }),
            ..
        }]
    ));

    let emitted = emit_rust_from_ir(&ir).expect("emit real clang neg_value from typed IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn neg_value(value: i32) -> i32"));
    assert!(rust.contains("return (-value);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-signed-unary-minus", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_parse_spec_report_uses_include_paths_for_real_ast_dump_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let source_root = unique_out_dir("clang-parse-spec-include-path");
    let include_dir = source_root.join("inc");
    let source_dir = source_root.join("src");
    fs::create_dir_all(&include_dir).unwrap();
    fs::create_dir_all(&source_dir).unwrap();
    fs::write(
        include_dir.join("fixture_config.h"),
        "int add_one(int value);\n#define ADD_ONE_OFFSET 1\n",
    )
    .unwrap();
    fs::write(
        source_dir.join("add_one.c"),
        "#include <fixture_config.h>\nint add_one(int value) { return value + ADD_ONE_OFFSET; }\n",
    )
    .unwrap();
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "source-sha",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + ADD_ONE_OFFSET; }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root.to_string_lossy().replace('\\', "/"),
        "source_file": "src/add_one.c",
        "source_file_hashes": {
            "src/add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/add_one.c",
            "line_start": 2,
            "line_end": 2,
            "byte_start": 28,
            "byte_end": 83,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "compiler_command_source": "unit-test",
            "clang_available": true
        }
    }))
    .unwrap();
    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_parse_spec_report(&environment, &parse_spec);

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.errors.is_empty(), "{:?}", report.errors);
    assert!(report.arguments.iter().any(|argument| {
        argument
            == &format!(
                "-I{}",
                source_root.join("inc").to_string_lossy().replace('\\', "/")
            )
    }));
    assert_eq!(
        report
            .function_ir
            .as_ref()
            .map(|function| function.name.as_str()),
        Some("add_one")
    );
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_uint32_integer_type_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-uint32-add-one");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("add_one.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t add_one(uint32_t value) { return value + 1; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "add_one");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert!(matches!(
        function.return_type.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    assert!(matches!(
        function.params[0].ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_const_void_pointer_and_size_t_params_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-void-size");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_identity.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\n#include <stdint.h>\nuint32_t crc_identity(uint32_t crc, const void *buf, size_t size) { return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_identity");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    assert_eq!(function.params.len(), 3);
    match &function.params[1].ty.kind {
        IrTypeKind::Pointer { pointee } => {
            assert!(!function.params[1].ty.is_const);
            assert!(matches!(pointee.kind, IrTypeKind::Void));
            assert!(pointee.is_const);
        }
        other => panic!("expected pointer param, got {other:?}"),
    }
    assert!(matches!(
        function.params[2].ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_const_uint8_pointer_decl_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-const-u8-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_decl.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_decl(uint32_t crc, const void *buf) { const uint8_t *p; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, ty, init, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected declaration followed by return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "p");
    assert!(init.is_none());
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => {
            assert!(!ty.is_const);
            assert!(matches!(
                pointee.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 8
                }
            ));
            assert!(pointee.is_const);
        }
        other => panic!("expected pointer declaration type, got {other:?}"),
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_assignment_statement_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-assignment-stmt");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_assign.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_assign(uint32_t crc) { crc = crc; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_assign");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(value, IrExpr::Var { name, .. } if name == "crc"));
}

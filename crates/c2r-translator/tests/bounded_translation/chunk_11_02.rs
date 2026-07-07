#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_initialized_decl_stmt_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-initialized-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_init.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_init(uint32_t crc) { uint32_t next = crc; return next; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_init");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name,
        init: Some(IrExpr::Var {
            name: init_name, ..
        }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected initialized decl followed by return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "next");
    assert_eq!(init_name, "crc");

    let rust = emit_rust_from_ir(function).expect("emit initialized decl from real clang AST");
    assert!(rust.contains("pub fn crc_init(crc: u32) -> u32"));
    assert!(rust.contains("let mut next: u32 = crc;"));
    assert!(rust.contains("return next;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-initialized-decl", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_uninitialized_local_decl_assigned_before_read_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-uninitialized-local-decl");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("assign_after_decl.c");
    fs::write(
        &source_file,
        "int assign_after_decl(void) { int tmp; tmp = 7; return tmp; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "assign_after_decl");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name, init: None, ..
    }, IrStmt::Assign {
        target,
        value: IrExpr::LitInt { value, .. },
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected uninitialized decl, assignment, and return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "tmp");
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "tmp"));
    assert_eq!(*value, 7);
    assert_eq!(return_name, "tmp");

    let emitted =
        emit_rust_from_ir(function).expect("emit assigned uninitialized local from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn assign_after_decl() -> i32"), "{rust}");
    assert!(rust.contains("let mut tmp: i32;"), "{rust}");
    assert!(rust.contains("tmp = 7i32;"), "{rust}");
    assert!(rust.contains("return tmp;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-real-clang-uninitialized-local-decl", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_local_fixed_array_initializer_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-local-array-init");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("lookup_local_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t lookup_local_table(size_t i) { uint32_t table[3] = {1U, 2U, 3U}; return table[i]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "lookup_local_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name,
        init: Some(IrExpr::ArrayLiteral { elements, .. }),
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Index { base, index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected local array declaration followed by index return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "table");
    assert_eq!(elements.len(), 3);
    assert!(matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "table"));
    assert!(matches!(index.as_ref(), IrExpr::Var { name, .. } if name == "i"));

    let rust = emit_rust_from_ir(function).expect("emit local array init from real clang AST");
    assert!(rust.contains("pub fn lookup_local_table(i: usize) -> u32"));
    assert!(rust.contains("let table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-local-array-init", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_local_fixed_array_index_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-local-array-index-assign");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("replace_local_table_slot.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t replace_local_table_slot(size_t i, uint32_t value) { uint32_t table[3] = {1U, 2U, 3U}; table[i] = value; return table[i]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "replace_local_table_slot",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, .. }, IrStmt::Assign { target, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected local array declaration, index assignment, and return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "table");
    assert!(matches!(target, IrExpr::Index { .. }));

    let rust = emit_rust_from_ir(function).expect("emit local array index assignment");
    assert!(rust.contains("pub fn replace_local_table_slot(i: usize, value: u32) -> u32"));
    assert!(rust.contains("let mut table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("table[i as usize] = value;"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-local-array-index-assignment", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_local_array_initializer_call_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-local-array-call-init-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("lookup_local_table_call_init.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t helper(void);\nuint32_t lookup_local_table_call_init(size_t i) { uint32_t table[3] = {helper(), 2U, 3U}; return table[i]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "lookup_local_table_call_init",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    let message = report
        .errors
        .first()
        .map(|error| error.message.as_str())
        .unwrap_or("");
    assert!(message.contains("InitListExpr"), "{message}");
    assert!(message.contains("initializer element 0"), "{message}");
    assert!(
        message.contains("only pure integer literal elements"),
        "{message}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_initialized_decl_with_direct_call_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-initialized-decl-call-lower");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("init_call.c");
    fs::write(
        &source_file,
        "int helper(void);\nint init_call(void) { int value = helper(); return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "init_call");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl {
        name,
        init: Some(IrExpr::Call { callee, args, .. }),
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected direct call initializer followed by return, got {:?}",
            function.body
        );
    };
    assert_eq!(name, "value");
    assert_eq!(callee, "helper");
    assert!(args.is_empty());

    let emitted =
        emit_rust_from_ir(function).expect("emit initialized direct call from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn init_call() -> i32"));
    assert!(rust.contains("let mut value: i32 = helper();"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-initialized-direct-call",
        &format!("fn helper() -> i32 {{ 0 }}\n{rust}"),
    );
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_strlen_model_with_target_abi_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let source_root = unique_out_dir("clang-real-strlen-target-abi-lower");
    let source_dir = source_root.join("src");
    fs::create_dir_all(&source_dir).unwrap();
    let source_file = source_dir.join("name_len.c");
    fs::write(
        &source_file,
        "typedef unsigned long size_t;\nsize_t strlen(const char *);\nsize_t name_len(const char *name) { return strlen(name); }\n",
    )
    .unwrap();
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "strlen-target-abi",
        "source_commit": "source-sha",
        "function_name": "name_len",
        "c_source": "size_t name_len(const char *name) { return strlen(name); }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root.to_string_lossy().replace('\\', "/"),
        "source_file": "src/name_len.c",
        "source_file_hashes": {
            "src/name_len.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/name_len.c",
            "line_start": 3,
            "line_end": 3,
            "byte_start": 63,
            "byte_end": 119,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "endianness": "little",
                "int_width": 32,
                "char_width": 8,
                "plain_char_signed": true,
                "short_width": 16,
                "long_width": 64,
                "long_long_width": 64,
                "pointer_width": 64
            },
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "x86_64-unknown-linux-gnu",
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
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Call {
            callee, args, ty, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected strlen return call, got {:?}", function.body);
    };
    assert_eq!(callee, "strlen");
    assert_eq!(args.len(), 1);
    assert_eq!(ty.spelled, "size_t");

    let emitted = emit_rust_from_ir(function).expect("emit strlen model from real clang AST");
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
    assert_rust_snippet_compiles("typed-ir-real-clang-strlen-model", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_nested_direct_call_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-nested-direct-call-lower");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("nested_direct_call.c");
    fs::write(
        &source_file,
        "int inner(int value) { return value + 1; }\nint outer(int value) { return value; }\nint nested_direct_call(int value) { return outer(inner(value)); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "nested_direct_call");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Call { callee, args, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected nested direct call return, got {:?}",
            function.body
        );
    };
    assert_eq!(callee, "outer");
    let [IrExpr::Call {
        callee: inner_callee,
        args: inner_args,
        ..
    }] = args.as_slice()
    else {
        panic!("expected one nested direct call arg, got {args:?}");
    };
    assert_eq!(inner_callee, "inner");
    assert_eq!(inner_args.len(), 1);

    let emitted = emit_rust_from_ir(function).expect("emit nested direct call from real clang AST");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn nested_direct_call(value: i32) -> i32"));
    assert!(rust.contains("return outer(inner(value));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-direct-call",
        &format!(
            "fn inner(value: i32) -> i32 {{ value + 1 }}\nfn outer(value: i32) -> i32 {{ value }}\n{rust}"
        ),
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_rejects_multiple_nested_direct_call_args_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-multiple-nested-direct-call-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("multiple_nested_direct_call.c");
    fs::write(
        &source_file,
        "int left(int value) { return value + 1; }\nint right(int value) { return value + 2; }\nint outer2(int a, int b) { return a + b; }\nint multiple_nested_direct_call(int value) { return outer2(left(value), right(value)); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "multiple_nested_direct_call",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    let message = report
        .errors
        .first()
        .map(|error| error.message.as_str())
        .unwrap_or("");
    assert!(
        message.contains("multiple nested call arguments are outside the bounded call subset"),
        "{message}"
    );
}

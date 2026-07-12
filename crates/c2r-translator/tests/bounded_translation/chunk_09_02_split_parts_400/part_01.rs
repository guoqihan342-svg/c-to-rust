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

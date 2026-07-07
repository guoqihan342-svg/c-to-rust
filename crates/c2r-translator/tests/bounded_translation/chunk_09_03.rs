#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_pointer_cast_assignment_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-cast-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_assign_ptr.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_assign_ptr(uint32_t crc, const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_assign_ptr");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Decl { name, init, .. }, IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] =
        function.body.as_slice()
    else {
        panic!(
            "expected declaration, pointer cast assignment, return; got {:?}",
            function.body
        );
    };
    assert_eq!(name, "p");
    assert!(init.is_none());
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "p"));
    match value {
        IrExpr::Cast {
            target,
            expr,
            implicit: false,
            ..
        } => {
            assert!(matches!(target.kind, IrTypeKind::Pointer { .. }));
            assert!(matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "buf"));
        }
        other => panic!("expected explicit cast value, got {other:?}"),
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_pointer_deref_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-deref");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte(const uint8_t *p) { return *p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_byte");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, ty, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected deref return, got {:?}", function.body);
    };
    assert!(matches!(ptr.as_ref(), IrExpr::Var { name, .. } if name == "p"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_pointer_deref_return_value_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-deref-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte(const uint8_t *p) { return *p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_byte");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit pointer deref return from real clang AST");
    let rust = &emitted.rust;
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn read_byte(p: &[u8]) -> u8"));
    assert!(rust.contains("return p[0usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-pointer-deref-emit", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_pointer_add_deref_return_values_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-add-deref-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_offset.c");
    fs::write(
        &source_file,
        concat!(
            "#include <stdint.h>\n",
            "#include <stddef.h>\n",
            "uint8_t read_pi(const uint8_t *p, size_t i) { return *(p + i); }\n",
            "uint8_t read_ip(const uint8_t *p, size_t i) { return *(i + p); }\n",
            "uint8_t read_p1(const uint8_t *p) { return *(p + 1); }\n",
        ),
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    for (function_name, signature, return_expr) in [
        (
            "read_pi",
            "pub fn read_pi(p: &[u8], i: usize) -> u8",
            "return p[i as usize];",
        ),
        (
            "read_ip",
            "pub fn read_ip(p: &[u8], i: usize) -> u8",
            "return p[i as usize];",
        ),
        (
            "read_p1",
            "pub fn read_p1(p: &[u8]) -> u8",
            "return p[1i32 as usize];",
        ),
    ] {
        let report =
            lower_function_from_clang_ast_dump_report(&environment, &source_file, function_name);

        assert_eq!(
            report.status, "lowered",
            "{function_name}: {:?}",
            report.errors
        );
        let function = report.function_ir.as_ref().expect("function ir");
        let emitted = emit_rust_from_ir(function)
            .unwrap_or_else(|error| panic!("{function_name}: {}", error.reason));
        let rust = &emitted.rust;
        assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
        assert!(rust.contains(signature), "{function_name}: {rust}");
        assert!(rust.contains(return_expr), "{function_name}: {rust}");
        assert_rust_snippet_compiles(
            &format!("typed-ir-real-clang-pointer-add-deref-emit-{function_name}"),
            rust,
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_pointer_add_deref_logical_not_if_condition_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-pointer-add-deref-logical-not-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("offset_is_zero_not.c");
    fs::write(
        &source_file,
        concat!(
            "#include <stdint.h>\n",
            "#include <stddef.h>\n",
            "int offset_is_zero_not(const uint8_t *p, size_t i) {\n",
            "    if (!*(p + i)) { return 1; }\n",
            "    return 0;\n",
            "}\n",
        ),
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "offset_is_zero_not");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit pointer add deref logical-not if from clang AST");
    let rust = &emitted.rust;
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn offset_is_zero_not(p: &[u8], i: usize) -> i32"));
    assert!(rust.contains("if p[i as usize] == 0u8 {"));
    assert!(rust.contains("return 1i32;"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-pointer-add-deref-logical-not-if", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_postfix_increment_deref_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-deref");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_inc.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_inc(const uint8_t *p) { return *p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_byte_inc");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected deref return, got {:?}", function.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        panic!("expected postfix increment ptr, got {ptr:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "p"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_deref_in_bitand_array_index_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-deref-bitand-array-index");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_index_deref.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_index_deref(uint32_t crc, const uint8_t *p) { return table[(crc ^ *p) & 0xff]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_index_deref");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        rhs,
        ..
    } = lhs.as_ref()
    else {
        panic!("expected bitxor lhs, got {lhs:?}");
    };
    assert!(matches!(
        without_implicit_cast(rhs.as_ref()),
        IrExpr::Deref { .. }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_postfix_increment_deref_in_bitand_array_index_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-postfix-increment-deref-bitand-array-index");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_index_postinc.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_index_postinc(uint32_t crc, const uint8_t *p) { return table[(crc ^ *p++) & 0xff]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_index_postinc");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        rhs,
        ..
    } = lhs.as_ref()
    else {
        panic!("expected bitxor lhs, got {lhs:?}");
    };
    let IrExpr::Deref { ptr, .. } = without_implicit_cast(rhs.as_ref()) else {
        panic!("expected deref rhs, got {rhs:?}");
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        panic!("expected postfix increment ptr, got {ptr:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "p"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_lowers_shift_right_expr_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-shift-right");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_shift.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_shift(uint32_t crc) { return crc >> 8; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_shift");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Shr,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected shift right return, got {:?}", function.body);
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 8, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_emits_bit_or_and_left_shift_when_enabled() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-bit-or-left-shift");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("pack_flags.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t pack_flags(uint32_t value) { return (value << 4) | 3U; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "pack_flags");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::BitOr,
                lhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected bit-or return, got {:?}", function.body);
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Shl,
            ..
        }
    ));

    let rust = emit_rust_from_ir(function).expect("emit bit-or left-shift from real clang AST");
    assert!(rust.contains("pub fn pack_flags(value: u32) -> u32"));
    assert!(rust.contains("checked_shl"));
    assert!(rust.contains("|"));
    assert_rust_snippet_compiles("typed-ir-real-clang-bit-or-left-shift", &rust);
}

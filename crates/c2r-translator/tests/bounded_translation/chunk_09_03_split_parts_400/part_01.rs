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

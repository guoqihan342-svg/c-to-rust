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

    let bump_point_x_for_step =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "bump_point_x_for_step")
            .expect("lower mutable record pointer field for-step fixture without invoking clang");
    let [IrStmt::For { step, .. }] = bump_point_x_for_step.function_ir.body.as_slice() else {
        panic!(
            "expected for-loop with record pointer field step, got {:?}",
            bump_point_x_for_step.function_ir.body
        );
    };
    assert!(
        matches!(
            step.as_deref(),
            Some(IrStmt::Assign {
                target: IrExpr::Member {
                    field,
                    is_arrow: true,
                    ..
                },
                ..
            }) if field == "x"
        ),
        "expected arrow member step assignment, got {step:?}"
    );
    let emitted = emit_rust_from_ir_with_globals(
        &bump_point_x_for_step.function_ir,
        &bump_point_x_for_step.globals,
    )
    .expect("emit Rust from mutable record pointer field for-step fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn bump_point_x_for_step(mut p: &mut Point, limit: i32)"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-record-arrow-for-step",
        rust,
        "let mut p = Point { x: 2i32, y: 0i32 };\nbump_point_x_for_step(&mut p, 3i32);\nassert_eq!(p.x, 5i32);",
    );
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
fn clang_ast_fixture_replays_integral_c_style_cast_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/integral_c_style_cast_ast.json"
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

    let narrow = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "narrow",
        Some(&target_abi),
    )
    .expect("lower clang-proven integral C-style cast fixture without invoking clang");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Cast {
                implicit,
                target,
                expr,
                ..
            }),
        ..
    }] = narrow.function_ir.body.as_slice()
    else {
        panic!(
            "expected integral C-style cast return to preserve an explicit IR cast, got {:?}",
            narrow.function_ir.body
        );
    };
    assert!(!implicit);
    assert!(matches!(
        target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    let IrExpr::LValueToRValue {
        target: read_ty,
        expr: read_expr,
        ..
    } = expr.as_ref()
    else {
        panic!("expected integral C-style cast operand to preserve LValueToRValue, got {expr:?}");
    };
    assert!(matches!(
        read_ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
    assert!(matches!(
        read_expr.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));

    let emitted = emit_rust_from_ir_with_globals(&narrow.function_ir, &narrow.globals)
        .expect("emit Rust from clang-proven integral C-style cast fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn narrow(value: u64) -> u32"),
        "{rust}"
    );
    assert!(rust.contains("return (value as u32);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-integral-c-style-cast",
        rust,
        "assert_eq!(narrow(0x1_0000_0001u64), 1u32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_integral_c_style_cast_without_target_abi() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/integral_c_style_cast_ast.json"
    ))
    .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "narrow")
        .expect_err("target-dependent C-style cast fixture must require target ABI");

    assert_eq!(error.kind, "unsupported_clang_type");
    assert!(
        error
            .message
            .contains("unsigned long requires target ABI width provenance"),
        "{error:?}"
    );
}

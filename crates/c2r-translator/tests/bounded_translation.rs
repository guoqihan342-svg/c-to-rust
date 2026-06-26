use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

#[cfg(feature = "typed-ir")]
use std::process::Command;

#[cfg(feature = "clang-frontend")]
use c2r_translator::clang_frontend::ClangParseSpec;
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
use c2r_translator::clang_frontend::{
    lower_function_from_clang_ast_dump, lower_function_from_clang_ast_dump_report,
    lower_function_from_clang_parse_spec_report, lower_function_skeleton,
    lower_function_skeleton_report, ClangBinaryOperator, ClangExprSkeleton, ClangFunctionSkeleton,
    ClangIncDecOperator, ClangParamSkeleton, ClangStmtSkeleton, ClangTypeKind, ClangTypeSkeleton,
    ClangUnaryOperator,
};
#[cfg(feature = "typed-ir")]
use c2r_translator::translation_route::{CandidateGenerator, CandidateRoute};
#[cfg(feature = "typed-ir")]
use c2r_translator::typed_ir::{
    emit_rust_from_ir, emit_rust_from_ir_with_globals, IrBinOp, IrExpr, IrFunction, IrGlobal,
    IrGlobalInit, IrIncDecOp, IrParam, IrStmt, IrType, IrTypeKind, IrUnOp,
};
use c2r_translator::{translate_slice, write_translation_artifacts, BuildProfile, SliceSpec};
use serde_json::Value;

fn profile(clang_available: bool) -> BuildProfile {
    BuildProfile {
        include_paths: vec!["/tmp/lib/include".to_string()],
        defines: vec!["_GNU_SOURCE".to_string()],
        target_triple: Some("x86_64-unknown-linux-gnu".to_string()),
        abi: Some("linux-gnu".to_string()),
        compiler_command_source: "compile_commands.json".to_string(),
        clang_available,
    }
}

fn unique_out_dir(name: &str) -> PathBuf {
    std::env::temp_dir().join(format!(
        "c2r-translator-test-{name}-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

fn json_file(path: PathBuf) -> Value {
    serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
}

#[cfg(feature = "clang-lowering-report")]
struct EnvVarGuard {
    key: &'static str,
    original: Option<std::ffi::OsString>,
}

#[cfg(feature = "clang-lowering-report")]
impl EnvVarGuard {
    fn set_path(key: &'static str, value: &std::path::Path) -> Self {
        let original = std::env::var_os(key);
        std::env::set_var(key, value);
        Self { key, original }
    }
}

#[cfg(feature = "clang-lowering-report")]
impl Drop for EnvVarGuard {
    fn drop(&mut self) {
        if let Some(value) = &self.original {
            std::env::set_var(self.key, value);
        } else {
            std::env::remove_var(self.key);
        }
    }
}

#[cfg(feature = "typed-ir")]
fn assert_rust_snippet_compiles(name: &str, rust_code: &str) {
    let out_dir = unique_out_dir(name);
    fs::create_dir_all(&out_dir).unwrap();
    let source = out_dir.join("lib.rs");
    let output = out_dir.join("lib.rlib");
    fs::write(&source, rust_code).unwrap();

    let rustc = std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into());
    let result = Command::new(rustc)
        .arg("--crate-type")
        .arg("lib")
        .arg(&source)
        .arg("-o")
        .arg(&output)
        .output()
        .unwrap_or_else(|error| panic!("failed to run rustc: {error}"));

    assert!(
        result.status.success(),
        "rustc failed for {name}\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&result.stdout),
        String::from_utf8_lossy(&result.stderr)
    );
    fs::remove_dir_all(out_dir).unwrap();
}

#[cfg(feature = "typed-ir")]
fn ir_integer(spelled: &str, canonical: &str, signed: bool, width: u16) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Integer { signed, width },
        is_const: false,
        width_bits: Some(width),
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_const(mut ty: IrType) -> IrType {
    ty.is_const = true;
    ty
}

#[cfg(feature = "typed-ir")]
fn ir_pointer(spelled: &str, canonical: &str, pointee: IrType, is_const: bool) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Pointer {
            pointee: Box::new(pointee),
        },
        is_const,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_u32() -> IrType {
    ir_integer("uint32_t", "unsigned int", false, 32)
}

#[cfg(feature = "typed-ir")]
fn ir_u8() -> IrType {
    ir_integer("uint8_t", "unsigned char", false, 8)
}

#[cfg(feature = "typed-ir")]
fn ir_usize() -> IrType {
    ir_integer("size_t", "unsigned long", false, 64)
}

#[cfg(feature = "typed-ir")]
fn ir_i32() -> IrType {
    ir_integer("int", "int", true, 32)
}

#[cfg(feature = "typed-ir")]
fn ir_void() -> IrType {
    IrType {
        spelled: "void".to_string(),
        canonical: "void".to_string(),
        kind: IrTypeKind::Void,
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_var(name: &str, ty: IrType) -> IrExpr {
    IrExpr::Var {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_lit(value: u64, spelling: &str, ty: IrType) -> IrExpr {
    IrExpr::LitInt {
        value,
        spelling: spelling.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_array(element: IrType, len: usize) -> IrType {
    IrType {
        spelled: format!("{}[{len}]", element.spelled),
        canonical: format!("{}[{len}]", element.canonical),
        kind: IrTypeKind::Array {
            element: Box::new(element),
            len: Some(len),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn without_implicit_cast(expr: &IrExpr) -> &IrExpr {
    match expr {
        IrExpr::Cast {
            expr,
            implicit: true,
            ..
        } => without_implicit_cast(expr),
        _ => expr,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Binary {
        op,
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_bitnot(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn flashdb_crc32_typed_ir() -> IrFunction {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        true,
    );
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        true,
    );

    let crc = || ir_var("crc", u32_ty.clone());
    let p = || ir_var("p", const_u8_ptr.clone());
    let size = || ir_var("size", usize_ty.clone());
    let crc32_table = || IrExpr::Var {
        name: "crc32_table".to_string(),
        ty: IrType {
            spelled: "const uint32_t[256]".to_string(),
            canonical: "const unsigned int[256]".to_string(),
            kind: IrTypeKind::Array {
                element: Box::new(u32_ty.clone()),
                len: Some(256),
            },
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        source_span: None,
    };

    let post_inc_p = IrExpr::IncDec {
        target: Box::new(p()),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty: const_u8_ptr.clone(),
        source_span: None,
    };
    let byte_read = IrExpr::Deref {
        ptr: Box::new(post_inc_p),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let promoted_byte = IrExpr::Cast {
        target: u32_ty.clone(),
        expr: Box::new(byte_read),
        implicit: true,
        source_span: None,
    };
    let table_index = ir_binary(
        IrBinOp::BitAnd,
        ir_binary(IrBinOp::BitXor, crc(), promoted_byte, u32_ty.clone()),
        ir_lit(0xFF, "0xFFU", u32_ty.clone()),
        u32_ty.clone(),
    );
    let table_lookup = IrExpr::Index {
        base: Box::new(crc32_table()),
        index: Box::new(table_index),
        ty: u32_ty.clone(),
        source_span: None,
    };
    let shift = ir_binary(
        IrBinOp::Shr,
        crc(),
        ir_lit(8, "8U", u32_ty.clone()),
        u32_ty.clone(),
    );

    IrFunction {
        name: "fdb_calc_crc32".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "buf".to_string(),
                ty: const_void_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "size".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: p(),
                value: IrExpr::Cast {
                    target: const_u8_ptr.clone(),
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Assign {
                target: crc(),
                value: ir_binary(
                    IrBinOp::BitXor,
                    crc(),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
                    u32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(size()),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: usize_ty,
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: crc(),
                    value: ir_binary(IrBinOp::BitXor, table_lookup, shift, u32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::BitXor,
                    crc(),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
                    u32_ty,
                )),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_u32_global_array(name: &str, len: usize, values: Vec<u64>) -> IrGlobal {
    let u32_ty = ir_u32();
    IrGlobal {
        name: name.to_string(),
        ty: IrType {
            spelled: format!("const uint32_t[{len}]"),
            canonical: format!("const unsigned int[{len}]"),
            kind: IrTypeKind::Array {
                element: Box::new(u32_ty),
                len: Some(len),
            },
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        init: if values.iter().all(|value| *value == 0) {
            IrGlobalInit::Zeroed
        } else {
            IrGlobalInit::IntegerArray(values)
        },
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn repeated_c_u32_initializer(len: usize, value: &str) -> String {
    std::iter::repeat_n(value, len)
        .collect::<Vec<_>>()
        .join(", ")
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_flashdb_crc32_without_readonly_global_table() {
    let error = emit_rust_from_ir(&flashdb_crc32_typed_ir())
        .expect_err("crc32 typed IR without a modeled readonly global table must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert!(!error.route.deprecated);
    assert!(error.reason.contains("crc32_table"));
    assert!(error.reason.contains("not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_flashdb_crc32_with_readonly_global_table_as_generic_route() {
    let global = ir_u32_global_array("crc32_table", 256, vec![0; 256]);
    let emitted = emit_rust_from_ir_with_globals(&flashdb_crc32_typed_ir(), &[global])
        .expect("emit flashdb crc32 through generic typed IR with global table");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32; 256];"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains(
        "crc = (CRC32_TABLE[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ (crc >> 8u32));"
    ));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-crc32-global-table-generic", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_global_array_initializer_length_mismatch() {
    let global = ir_u32_global_array("table", 4, vec![1, 2]);
    let ir = IrFunction {
        name: "return_zero".to_string(),
        return_type: ir_u32(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0U", ir_u32())),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir_with_globals(&ir, &[global])
        .expect_err("global initializer length mismatch must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error
        .reason
        .contains("initializer length 2 does not match array length 4"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_fixed_array_index_read() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let table_ty = ir_array(u32_ty.clone(), 3);
    let ir = IrFunction {
        name: "lookup_local_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "i".to_string(),
            ty: usize_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1U", u32_ty.clone()),
                        ir_lit(2, "2U", u32_ty.clone()),
                        ir_lit(3, "3U", u32_ty.clone()),
                    ],
                    ty: table_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Index {
                    base: Box::new(ir_var("table", table_ty)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: u32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit local fixed array index read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-local-fixed-array-index-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_fixed_array_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let table_ty = ir_array(u32_ty.clone(), 3);
    let table_var = || ir_var("table", table_ty.clone());
    let index_var = || ir_var("i", usize_ty.clone());
    let ir = IrFunction {
        name: "replace_local_table_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1U", u32_ty.clone()),
                        ir_lit(2, "2U", u32_ty.clone()),
                        ir_lit(3, "3U", u32_ty.clone()),
                    ],
                    ty: table_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(table_var()),
                    index: Box::new(index_var()),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_var("value", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Index {
                    base: Box::new(table_var()),
                    index: Box::new(index_var()),
                    ty: u32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit local fixed array index assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let mut table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("table[i as usize] = value;"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("typed-ir-local-fixed-array-index-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_global_array_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let global = ir_u32_global_array("table", 3, vec![1, 2, 3]);
    let ir = IrFunction {
        name: "write_global_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "i".to_string(),
            ty: usize_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("table", global.ty.clone())),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(0, "0U", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0U", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir_with_globals(&ir, &[global])
        .expect_err("readonly global array assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("assign index base table"));
    assert!(error.reason.contains("readonly global"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_pointer_index_assignment() {
    let u32_ty = ir_u32();
    let usize_ty = ir_usize();
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "write_const_pointer_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "table".to_string(),
                ty: const_u32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "i".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Index {
                    base: Box::new(ir_var("table", const_u32_ptr)),
                    index: Box::new(ir_var("i", usize_ty)),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                value: ir_lit(0, "0U", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0U", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("const pointer index assignment must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("assign index base table"));
    assert!(error.reason.contains("unsupported type"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_local_fixed_array_index_read_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let u32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let usize_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let table_ty = ClangTypeSkeleton {
        spelled: "uint32_t[3]".to_string(),
        canonical: "uint32_t[3]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(u32_ty.clone()),
            len: Some(3),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "lookup_local_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "i".to_string(),
            ty: usize_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(ClangExprSkeleton::ArrayLiteral {
                    elements: vec![
                        ClangExprSkeleton::Cast {
                            target: u32_ty.clone(),
                            expr: Box::new(ClangExprSkeleton::IntegerLiteral {
                                value: 1,
                                spelling: "1".to_string(),
                                ty: int_ty,
                            }),
                            implicit: true,
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 2,
                            spelling: "2U".to_string(),
                            ty: u32_ty.clone(),
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 3,
                            spelling: "3U".to_string(),
                            ty: u32_ty.clone(),
                        },
                    ],
                    ty: table_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::Index {
                    base: Box::new(ClangExprSkeleton::DeclRef {
                        name: "table".to_string(),
                        ty: table_ty,
                    }),
                    index: Box::new(ClangExprSkeleton::DeclRef {
                        name: "i".to_string(),
                        ty: usize_ty,
                    }),
                    ty: u32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower local fixed array skeleton");
    let emitted = emit_rust_from_ir(&ir).expect("emit local fixed array from clang-lowered IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let table: [u32; 3] = [(1i32 as u32), 2u32, 3u32];"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("clang-lowered-local-fixed-array-index-read", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_local_fixed_array_index_assignment_from_clang_lowered_ir() {
    let u32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let usize_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let table_ty = ClangTypeSkeleton {
        spelled: "uint32_t[3]".to_string(),
        canonical: "uint32_t[3]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(u32_ty.clone()),
            len: Some(3),
        },
    };
    let table_ref = || ClangExprSkeleton::DeclRef {
        name: "table".to_string(),
        ty: table_ty.clone(),
    };
    let index_ref = || ClangExprSkeleton::DeclRef {
        name: "i".to_string(),
        ty: usize_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "replace_local_table_slot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "i".to_string(),
                ty: usize_ty.clone(),
            },
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: u32_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "table".to_string(),
                ty: table_ty.clone(),
                init: Some(ClangExprSkeleton::ArrayLiteral {
                    elements: vec![
                        ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1U".to_string(),
                            ty: u32_ty.clone(),
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 2,
                            spelling: "2U".to_string(),
                            ty: u32_ty.clone(),
                        },
                        ClangExprSkeleton::IntegerLiteral {
                            value: 3,
                            spelling: "3U".to_string(),
                            ty: u32_ty.clone(),
                        },
                    ],
                    ty: table_ty.clone(),
                }),
            },
            ClangStmtSkeleton::Assign {
                target: ClangExprSkeleton::Index {
                    base: Box::new(table_ref()),
                    index: Box::new(index_ref()),
                    ty: u32_ty.clone(),
                },
                value: ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: u32_ty.clone(),
                },
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::Index {
                    base: Box::new(table_ref()),
                    index: Box::new(index_ref()),
                    ty: u32_ty.clone(),
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower local array assignment skeleton");
    let [IrStmt::Decl { .. }, IrStmt::Assign { target, .. }, IrStmt::Return { .. }] =
        ir.body.as_slice()
    else {
        panic!(
            "expected local array declaration, assignment, and return, got {:?}",
            ir.body
        );
    };
    assert!(matches!(target, IrExpr::Index { .. }));

    let emitted =
        emit_rust_from_ir(&ir).expect("emit local array assignment from clang-lowered IR");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("let mut table: [u32; 3] = [1u32, 2u32, 3u32];"));
    assert!(rust.contains("table[i as usize] = value;"));
    assert!(rust.contains("return table[i as usize];"));
    assert_rust_snippet_compiles("clang-lowered-local-fixed-array-index-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_does_not_use_deprecated_crc32_route_for_no_globals_crc32() {
    let error = emit_rust_from_ir(&flashdb_crc32_typed_ir())
        .expect_err("no-globals crc32 must not be emitted through a canned legacy route");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert!(!error.route.deprecated);
    assert!(error.route.delete_when.is_empty());
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_reports_generic_candidate_route_for_scalar_emit() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "add_one_route".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Add,
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar route");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert_eq!(
        emitted.route.candidate_generator,
        CandidateGenerator::GenericTypedIrEmitter
    );
    assert!(!emitted.route.deprecated);
    assert!(emitted.rust.contains("pub fn add_one_route"));
    assert!(!emitted.rust.contains("crc32_update_byte"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_subtraction() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sub_one".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Sub,
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar subtraction");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(rust.contains("return (value - 1i32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-scalar-subtraction", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_mul_div_mod() {
    let i32_ty = ir_i32();
    let mul = ir_binary(
        IrBinOp::Mul,
        ir_var("value", i32_ty.clone()),
        ir_lit(3, "3", i32_ty.clone()),
        i32_ty.clone(),
    );
    let div = ir_binary(
        IrBinOp::Div,
        mul,
        ir_lit(2, "2", i32_ty.clone()),
        i32_ty.clone(),
    );
    let rem = ir_binary(
        IrBinOp::Mod,
        div,
        ir_lit(5, "5", i32_ty.clone()),
        i32_ty.clone(),
    );
    let ir = IrFunction {
        name: "mul_div_mod".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(rem),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar mul/div/mod");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn mul_div_mod(value: i32) -> i32"));
    assert!(rust.contains("return (((value * 3i32) / 2i32) % 5i32);"));
    assert_rust_snippet_compiles("typed-ir-scalar-mul-div-mod", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_identifier_call_expressions() {
    let i32_ty = ir_i32();
    let helper_call = |arg: IrExpr| IrExpr::Call {
        callee: "helper".to_string(),
        args: vec![arg],
        ty: i32_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "first".to_string(),
                ty: i32_ty.clone(),
                init: Some(helper_call(ir_var("value", i32_ty.clone()))),
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("value", i32_ty.clone()),
                value: helper_call(ir_var("first", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(helper_call(ir_var("value", i32_ty.clone()))),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call expressions");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_expression(mut value: i32) -> i32"));
    assert!(rust.contains("let mut first: i32 = helper(value);"));
    assert!(rust.contains("value = helper(first);"));
    assert!(rust.contains("return helper(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-expressions",
        &format!("fn helper(value: i32) -> i32 {{ value }}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_direct_identifier_call_statement() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "call_hook".to_string(),
        return_type: void_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![ir_var("value", i32_ty)],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit direct call statement");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn call_hook(value: i32)"));
    assert!(rust.contains("observe(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-direct-call-statement",
        &format!("fn observe(_: i32) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nested_direct_call_arguments() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "nested_call_expression".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![IrExpr::Call {
                    callee: "other".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                }],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("nested call arg must fail closed");

    assert!(error
        .reason
        .contains("nested call expressions are outside the bounded call subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_side_effect_direct_call_arguments() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "side_effect_call_argument".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "helper".to_string(),
                args: vec![IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                }],
                ty: i32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("side-effect call arg must fail closed");

    assert!(error
        .reason
        .contains("call arguments cannot use increment/decrement value semantics"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_index_over_const_u32_pointer_param() {
    let u32_ty = ir_u32();
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "table".to_string(),
                ty: const_u32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "idx".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Index {
                base: Box::new(ir_var("table", const_u32_ptr)),
                index: Box::new(ir_var("idx", u32_ty.clone())),
                ty: u32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit const u32 pointer index");

    assert!(rust.contains("pub fn read_table(table: &[u32], idx: u32) -> u32"));
    assert!(rust.contains("return table[idx as usize];"));
    assert_rust_snippet_compiles("typed-ir-const-u32-pointer-index", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_crc_update_assignment_with_nested_byte_read() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let table_index = ir_binary(
        IrBinOp::BitAnd,
        ir_binary(
            IrBinOp::BitXor,
            ir_var("crc", u32_ty.clone()),
            IrExpr::Cast {
                target: u32_ty.clone(),
                expr: Box::new(byte_read),
                implicit: true,
                source_span: None,
            },
            u32_ty.clone(),
        ),
        ir_lit(0xFF, "0xFFU", u32_ty.clone()),
        u32_ty.clone(),
    );
    let table_lookup = IrExpr::Index {
        base: Box::new(ir_var("table", const_u32_ptr.clone())),
        index: Box::new(table_index),
        ty: u32_ty.clone(),
        source_span: None,
    };
    let shift = ir_binary(
        IrBinOp::Shr,
        ir_var("crc", u32_ty.clone()),
        ir_lit(8, "8U", u32_ty.clone()),
        u32_ty.clone(),
    );
    let ir = IrFunction {
        name: "update_crc_step".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr,
                source_span: None,
            },
            IrParam {
                name: "table".to_string(),
                ty: const_u32_ptr,
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: ir_var("crc", u32_ty.clone()),
                value: ir_binary(IrBinOp::BitXor, table_lookup, shift, u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("crc", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit crc update assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("pub fn update_crc_step(mut crc: u32, p: &[u8], table: &[u32]) -> u32"));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(
        rust.contains("crc = (table[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ (crc >> 8u32));")
    );
    assert!(rust.contains("return crc;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-crc-update-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_post_increment_reads_in_assign_value() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = || IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_assign_double_byte_read".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: ir_var("crc", u32_ty.clone()),
                value: ir_binary(
                    IrBinOp::BitXor,
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read()),
                        implicit: true,
                        source_span: None,
                    },
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read()),
                        implicit: true,
                        source_span: None,
                    },
                    u32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("crc", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("assign with multiple byte reads must fail closed");

    assert!(error
        .reason
        .contains("assign value multiple post-increment byte reads are unsupported"));
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert_eq!(error.route.fallback, None);
    assert!(error.route.reasons.iter().any(|reason| reason
        .detail
        .contains("assign value multiple post-increment byte reads are unsupported")));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_const_u8_pointer_param_post_increment_read() {
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_byte".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Deref {
                ptr: Box::new(IrExpr::IncDec {
                    target: Box::new(ir_var("p", const_u8_ptr.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: const_u8_ptr,
                    source_span: None,
                }),
                ty: u8_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit const u8 post-increment read");

    assert!(rust.contains("pub fn read_byte(p: &[u8]) -> u8"));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(rust.contains("return byte0;"));
    assert_rust_snippet_compiles("typed-ir-const-u8-post-increment-read", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_const_void_cast_cursor_post_increment_read() {
    let u8_ty = ir_u8();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        true,
    );
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_byte_from_void".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "buf".to_string(),
            ty: const_void_ptr.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("p", const_u8_ptr.clone()),
                value: IrExpr::Cast {
                    target: const_u8_ptr.clone(),
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Deref {
                    ptr: Box::new(IrExpr::IncDec {
                        target: Box::new(ir_var("p", const_u8_ptr.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: const_u8_ptr,
                        source_span: None,
                    }),
                    ty: u8_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit const void byte cursor read");

    assert!(rust.contains("pub fn read_byte_from_void(buf: &[u8]) -> u8"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return byte0;"));
    assert_rust_snippet_compiles("typed-ir-const-void-byte-cursor-read", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_const_void_cast_cursor_nested_post_increment_read_in_binary_expr() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        false,
    );
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "crc_xor_byte".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "buf".to_string(),
                ty: const_void_ptr.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("p", const_u8_ptr.clone()),
                value: IrExpr::Cast {
                    target: const_u8_ptr,
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_binary(
                    IrBinOp::BitXor,
                    ir_var("crc", u32_ty.clone()),
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read),
                        implicit: true,
                        source_span: None,
                    },
                    u32_ty.clone(),
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit nested post-increment byte read");

    assert!(rust.contains("pub fn crc_xor_byte(crc: u32, buf: &[u8]) -> u32"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles("typed-ir-nested-post-increment-byte-read", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_avoids_byte_temp_name_collision_for_nested_post_increment_read() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "crc_xor_byte_collision".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr,
                source_span: None,
            },
            IrParam {
                name: "byte0".to_string(),
                ty: u8_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                ir_var("crc", u32_ty.clone()),
                IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(byte_read),
                    implicit: true,
                    source_span: None,
                },
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit nested byte read without temp collision");

    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte1: u8 = p[p_index];"));
    assert!(rust.contains("return (crc ^ (byte1 as u32));"));
    assert_rust_snippet_compiles("typed-ir-nested-byte-temp-collision", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_avoids_cursor_temp_name_collision_for_nested_post_increment_read() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "crc_xor_byte_cursor_collision".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "p".to_string(),
                ty: const_u8_ptr,
                source_span: None,
            },
            IrParam {
                name: "p_index".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                ir_binary(
                    IrBinOp::BitXor,
                    ir_var("crc", u32_ty.clone()),
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(byte_read),
                        implicit: true,
                        source_span: None,
                    },
                    u32_ty.clone(),
                ),
                ir_var("p_index", u32_ty.clone()),
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit nested byte read without cursor collision");

    assert!(rust.contains("let mut p_index1: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index1];"));
    assert!(rust.contains("p_index1 += 1;"));
    assert!(rust.contains("return ((crc ^ (byte0 as u32)) ^ p_index);"));
    assert_rust_snippet_compiles("typed-ir-nested-byte-cursor-collision", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_undeclared_var_named_like_generated_byte_temp() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "bad_generated_temp_ref".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(byte_read),
                    implicit: true,
                    source_span: None,
                },
                ir_var("byte0", u32_ty.clone()),
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("generated temp must not declare source var");

    assert!(error.reason.contains("return expr binary rhs"));
    assert!(error.reason.contains("var byte0 is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_multiple_nested_post_increment_reads_in_one_expr() {
    let u8_ty = ir_u8();
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let byte_read = || IrExpr::Deref {
        ptr: Box::new(IrExpr::IncDec {
            target: Box::new(ir_var("p", const_u8_ptr.clone())),
            op: IrIncDecOp::Inc,
            prefix: false,
            ty: const_u8_ptr.clone(),
            source_span: None,
        }),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let ir = IrFunction {
        name: "double_byte_read".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u8_ptr.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitXor,
                byte_read(),
                byte_read(),
                u8_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("multiple post-increment reads must fail closed");

    assert!(error
        .reason
        .contains("multiple post-increment byte reads are unsupported"));
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert_eq!(error.route.candidate_generator, CandidateGenerator::None);
    assert_eq!(error.route.fallback, None);
    assert!(error.route.reasons.iter().any(|reason| reason
        .detail
        .contains("multiple post-increment byte reads are unsupported")));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_postfix_decrement_while_condition_for_size_counter() {
    let usize_ty = ir_usize();
    let ir = IrFunction {
        name: "countdown_sum".to_string(),
        return_type: usize_ty.clone(),
        params: vec![
            IrParam {
                name: "size".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "acc".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("size", usize_ty.clone())),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: usize_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("acc", usize_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("acc", usize_ty.clone()),
                        ir_var("size", usize_ty.clone()),
                        usize_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("acc", usize_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit postfix decrement while condition");

    assert!(rust.contains("pub fn countdown_sum(mut size: usize, mut acc: usize) -> usize"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("let size_before_dec0: usize = size;"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size_before_dec0 == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("acc = (acc + size);"));
    assert!(rust.contains("return acc;"));
    assert_rust_snippet_compiles("typed-ir-postfix-decrement-while", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_void_cast_cursor_without_byte_read() {
    let u8_ty = ir_u8();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        false,
    );
    let const_u8_ptr = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(u8_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "cast_without_read".to_string(),
        return_type: u8_ty.clone(),
        params: vec![IrParam {
            name: "buf".to_string(),
            ty: const_void_ptr.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("p", const_u8_ptr),
                value: IrExpr::Cast {
                    target: ir_pointer(
                        "const uint8_t *",
                        "const unsigned char *",
                        ir_const(u8_ty.clone()),
                        false,
                    ),
                    expr: Box::new(ir_var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", u8_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("cast without byte read must fail closed");

    assert!(error
        .reason
        .contains("param buf has pointer type const void * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_const_u32_pointer_param_post_increment_read() {
    let u32_ty = ir_u32();
    let const_u32_ptr = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        ir_const(u32_ty.clone()),
        false,
    );
    let ir = IrFunction {
        name: "read_word".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_u32_ptr.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Deref {
                ptr: Box::new(IrExpr::IncDec {
                    target: Box::new(ir_var("p", const_u32_ptr.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: const_u32_ptr,
                    source_span: None,
                }),
                ty: u32_ty.clone(),
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("u32 post-increment read must fail closed");

    assert!(error
        .reason
        .contains("post-increment cursor p has unsupported type const uint32_t *"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_pointer_param_in_generic_emitter() {
    let i32_ty = ir_i32();
    let mutable_i32_ptr = ir_pointer("int *", "int *", i32_ty, false);
    let ir = IrFunction {
        name: "mutable_pointer".to_string(),
        return_type: IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: false,
            width_bits: None,
            source_span: None,
        },
        params: vec![IrParam {
            name: "out".to_string(),
            ty: mutable_i32_ptr,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: None,
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("mutable pointer param must fail closed");

    assert!(error
        .reason
        .contains("param out has pointer type int * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_non_const_pointer_param_in_generic_emitter() {
    let u32_ty = ir_u32();
    let mutable_u32_ptr = ir_pointer("uint32_t *", "unsigned int *", u32_ty.clone(), false);
    let ir = IrFunction {
        name: "read_mutable_table".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "table".to_string(),
                ty: mutable_u32_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "idx".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Index {
                base: Box::new(ir_var("table", mutable_u32_ptr)),
                index: Box::new(ir_var("idx", u32_ty.clone())),
                ty: u32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-const pointer param must fail closed");

    assert!(error
        .reason
        .contains("param table has pointer type uint32_t * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_crc32_loop_with_extra_top_level_term() {
    let mut ir = flashdb_crc32_typed_ir();
    let IrStmt::While { body, .. } = &mut ir.body[3] else {
        panic!("expected crc32 while loop");
    };
    let IrStmt::Assign { value, .. } = &mut body[0] else {
        panic!("expected crc32 assignment");
    };
    let original = value.clone();
    *value = ir_binary(
        IrBinOp::BitXor,
        original,
        ir_lit(1, "1U", ir_u32()),
        ir_u32(),
    );

    let error = emit_rust_from_ir(&ir).expect_err("extra top-level term must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_assignment_to_mut_param() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "invert_crc".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "crc".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: ir_var("crc", u32_ty.clone()),
                value: ir_binary(
                    IrBinOp::BitXor,
                    ir_var("crc", u32_ty.clone()),
                    ir_bitnot(ir_lit(0, "0U", u32_ty.clone()), u32_ty.clone()),
                    u32_ty.clone(),
                ),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("crc", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar param assignment");

    assert!(rust.contains("pub fn invert_crc(mut crc: u32) -> u32"));
    assert!(rust.contains("crc = (crc ^ !0u32);"));
    assert!(rust.contains("return crc;"));
    assert_rust_snippet_compiles("typed-ir-scalar-assignment", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_decl_init_and_integer_cast() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "widen".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: Some(IrExpr::Cast {
                    target: u32_ty.clone(),
                    expr: Box::new(ir_var("value", i32_ty.clone())),
                    implicit: false,
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar decl and cast");

    assert!(rust.contains("pub fn widen(value: i32) -> u32"));
    assert!(rust.contains("let mut tmp: u32 = (value as u32);"));
    assert!(rust.contains("return tmp;"));
    assert_rust_snippet_compiles("typed-ir-scalar-decl-cast", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_while_with_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "countdown".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("count", i32_ty.clone()),
                        ir_bitnot(ir_lit(0, "0", i32_ty.clone()), i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while");

    assert!(rust.contains("pub fn countdown(mut count: i32) -> i32"));
    assert!(rust.contains("while count != 0i32 {"));
    assert!(rust.contains("count = (count + !0i32);"));
    assert!(rust.contains("return count;"));
    assert_rust_snippet_compiles("typed-ir-scalar-while", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_unsupported_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_var("count", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while call condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error
        .reason
        .contains("call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_incdec_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("count", i32_ty.clone())),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: ir_var("count", i32_ty.clone()),
                    value: ir_var("count", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while incdec condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_with_non_var_assignment_target() {
    let i32_ty = ir_i32();
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_while_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Assign {
                    target: IrExpr::Deref {
                        ptr: Box::new(ir_var("ptr", pointer_ty)),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    value: ir_lit(1, "1", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("count", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while non-var assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].while body[0]"));
    assert!(error
        .reason
        .contains("assign target must be Var or local fixed array Index"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_while_body_decl_scope_leak() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_while_scope".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "count".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_var("count", i32_ty.clone()),
                body: vec![IrStmt::Decl {
                    name: "tmp".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("while body decl must not leak");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("var tmp is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_else_with_integer_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "adjust".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_var("flag", i32_ty.clone()),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                else_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_bitnot(ir_lit(0, "0", i32_ty.clone()), i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if");

    assert!(rust.contains("pub fn adjust(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = (value + 1i32);"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = (value + !0i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_with_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "adjust_positive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if comparison condition");

    assert!(rust.contains("pub fn adjust_positive(mut value: i32) -> i32"));
    assert!(rust.contains("if (value > 0i32) {"));
    assert!(rust.contains("value = (value + 1i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-scalar-if-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_if_with_casted_comparison_literal() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "adjust_unsigned_positive".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", u32_ty.clone()),
                    IrExpr::Cast {
                        target: u32_ty.clone(),
                        expr: Box::new(ir_lit(0, "0", i32_ty.clone())),
                        implicit: true,
                        source_span: None,
                    },
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", u32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", u32_ty.clone()),
                        ir_lit(1, "1", u32_ty.clone()),
                        u32_ty.clone(),
                    ),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", u32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if casted comparison literal");

    assert!(rust.contains("pub fn adjust_unsigned_positive(mut value: u32) -> u32"));
    assert!(rust.contains("if (value > (0i32 as u32)) {"));
    assert!(rust.contains("value = (value + 1u32);"));
    assert_rust_snippet_compiles("typed-ir-scalar-if-casted-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_all_scalar_comparison_conditions_without_integer_truthiness_wrap() {
    let cases = vec![
        (IrBinOp::Lt, "<", "lt"),
        (IrBinOp::Le, "<=", "le"),
        (IrBinOp::Gt, ">", "gt"),
        (IrBinOp::Ge, ">=", "ge"),
        (IrBinOp::Eq, "==", "eq"),
        (IrBinOp::Neq, "!=", "neq"),
    ];

    for (op, expected, suffix) in cases {
        let i32_ty = ir_i32();
        let ir = IrFunction {
            name: format!("cmp_{suffix}"),
            return_type: i32_ty.clone(),
            params: vec![IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            }],
            body: vec![
                IrStmt::If {
                    condition: ir_binary(
                        op,
                        ir_var("value", i32_ty.clone()),
                        ir_lit(0, "0", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    then_body: vec![IrStmt::Assign {
                        target: ir_var("value", i32_ty.clone()),
                        value: ir_binary(
                            IrBinOp::Add,
                            ir_var("value", i32_ty.clone()),
                            ir_lit(1, "1", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    }],
                    else_body: vec![],
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(ir_var("value", i32_ty.clone())),
                    source_span: None,
                },
            ],
            source_span: None,
        };

        let rust = emit_rust_from_ir(&ir).expect("emit scalar comparison condition");

        assert!(rust.contains(&format!("if (value {expected} 0i32) {{")));
        assert!(!rust.contains(&format!("(value {expected} 0i32) != 0i32")));
        assert_rust_snippet_compiles(&format!("typed-ir-scalar-if-comparison-{suffix}"), &rust);
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_scalar_while_with_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "countdown_positive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::While {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("value", i32_ty.clone()),
                        ir_bitnot(ir_lit(0, "0", i32_ty.clone()), i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while comparison condition");

    assert!(rust.contains("pub fn countdown_positive(mut value: i32) -> i32"));
    assert!(rust.contains("while (value > 0i32) {"));
    assert!(!rust.contains("(value > 0i32) != 0i32"));
    assert!(rust.contains("value = (value + !0i32);"));
    assert_rust_snippet_compiles("typed-ir-scalar-while-comparison", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_expression_outside_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "positive_as_int".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Gt,
                ir_var("value", i32_ty.clone()),
                ir_lit(0, "0", i32_ty.clone()),
                i32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison outside condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr"));
    assert!(error.reason.contains("binary op Gt is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_mismatched_operand_types() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_cmp_types".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "left".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "right".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Lt,
                    ir_var("left", i32_ty.clone()),
                    ir_var("right", u32_ty),
                    i32_ty.clone(),
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("left", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("mismatched comparison types must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("comparison operand types must match for <"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_non_int_result_type() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_cmp_result_type".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Gt,
                    ir_var("value", i32_ty.clone()),
                    ir_lit(0, "0", i32_ty.clone()),
                    u32_ty,
                ),
                then_body: vec![],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("non-int comparison result must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("comparison result type must be C int"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_comparison_condition_with_incdec_operand() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_cmp_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    IrExpr::IncDec {
                        target: Box::new(ir_var("value", i32_ty.clone())),
                        op: IrIncDecOp::Inc,
                        prefix: false,
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("comparison incdec operand must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("comparison lhs"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_unsupported_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_call".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![],
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if call condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_call_in_comparison_condition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_call_comparison".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_binary(
                    IrBinOp::Eq,
                    IrExpr::Call {
                        callee: "helper".to_string(),
                        args: vec![ir_var("value", i32_ty.clone())],
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    ir_lit(0, "0", i32_ty.clone()),
                    i32_ty.clone(),
                ),
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if comparison call condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error
        .reason
        .contains("call expression helper is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_incdec_condition_expr() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_incdec".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: IrExpr::IncDec {
                    target: Box::new(ir_var("value", i32_ty.clone())),
                    op: IrIncDecOp::Inc,
                    prefix: false,
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                then_body: vec![IrStmt::Assign {
                    target: ir_var("value", i32_ty.clone()),
                    value: ir_var("value", i32_ty.clone()),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if incdec condition must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_with_non_var_assignment_target() {
    let i32_ty = ir_i32();
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "bad_if_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_var("value", i32_ty.clone()),
                then_body: vec![],
                else_body: vec![IrStmt::Assign {
                    target: IrExpr::Deref {
                        ptr: Box::new(ir_var("ptr", pointer_ty)),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    value: ir_lit(1, "1", i32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if non-var assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("stmt[0].if else[0]"));
    assert!(error
        .reason
        .contains("assign target must be Var or local fixed array Index"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_if_body_decl_scope_leak() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_if_scope".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "flag".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: ir_var("flag", i32_ty.clone()),
                then_body: vec![IrStmt::Decl {
                    name: "tmp".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(1, "1", i32_ty.clone())),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("if body decl must not leak");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("var tmp is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_pointer_param_in_generic_emitter() {
    let u32_ty = ir_u32();
    let const_void_ptr = ir_pointer(
        "const void *",
        "const void *",
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const: true,
            width_bits: None,
            source_span: None,
        },
        true,
    );
    let ir = IrFunction {
        name: "read_byte".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "buf".to_string(),
            ty: const_void_ptr,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(0, "0U", u32_ty.clone())),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("pointer param must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("param buf has pointer type const void * is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mismatched_binary_operand_types_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "mask".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "x".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::BitAnd,
                ir_var("x", u32_ty.clone()),
                ir_lit(0xFF, "0xFF", i32_ty),
                u32_ty.clone(),
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("mismatched binary types must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("binary operand types must match"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mismatched_mul_div_mod_operand_types_in_generic_emitter() {
    for (op, symbol, name) in [
        (IrBinOp::Mul, "*", "bad_multiplicative_mul"),
        (IrBinOp::Div, "/", "bad_multiplicative_div"),
        (IrBinOp::Mod, "%", "bad_multiplicative_mod"),
    ] {
        let u32_ty = ir_u32();
        let i32_ty = ir_i32();
        let ir = IrFunction {
            name: name.to_string(),
            return_type: u32_ty.clone(),
            params: vec![IrParam {
                name: "x".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            }],
            body: vec![IrStmt::Return {
                value: Some(ir_binary(
                    op,
                    ir_var("x", u32_ty.clone()),
                    ir_lit(2, "2", i32_ty),
                    u32_ty.clone(),
                )),
                source_span: None,
            }],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).expect_err("mismatched binary types must fail closed");

        assert!(
            error
                .reason
                .contains("outside the current typed IR emitter subset"),
            "{symbol} produced unexpected error: {}",
            error.reason
        );
        assert!(
            error.reason.contains(&format!(
                "binary operand types must match result type for {symbol}"
            )),
            "{symbol} produced unexpected error: {}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_return_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_return".to_string(),
        return_type: u32_ty,
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("return type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("return expr type i32"));
    assert!(error.reason.contains("expected type u32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_assign_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_assign".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "x".to_string(),
            ty: u32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Assign {
                target: ir_var("x", u32_ty.clone()),
                value: ir_lit(1, "1", i32_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("x", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("assign type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("assign value type i32"));
    assert!(error.reason.contains("expected type u32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_decl_init_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: Some(ir_lit(1, "1", i32_ty)),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("decl init type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("decl tmp initializer type i32"));
    assert!(error.reason.contains("expected type u32"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_bitnot_operand_type_mismatch_in_generic_emitter() {
    let u32_ty = ir_u32();
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "bad_bitnot".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "x".to_string(),
            ty: u8_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_bitnot(ir_var("x", u8_ty), u32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("bitnot operand type mismatch must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("bitnot operand type u8"));
    assert!(error.reason.contains("expected type u32"));
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
fn typed_ir_rejects_uninitialized_decl_in_generic_emitter() {
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

    let error = emit_rust_from_ir(&ir).expect_err("uninitialized decl must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("decl tmp without initializer is unsupported"));
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

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn add_one(value: i32) -> i32"));
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
    assert_eq!(dry_run.status, "ready_without_libclang");
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
        .contains(&"libclang execution is not enabled in this dry-run skeleton".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_dry_run_records_missing_libclang_environment_without_parsing() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
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
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let environment = std::collections::BTreeMap::new();

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run_with_environment(&environment);

    assert_eq!(dry_run.status, "ready_without_libclang");
    assert_eq!(dry_run.environment.status, "not_configured");
    assert_eq!(dry_run.environment.source.as_deref(), None);
    assert_eq!(dry_run.environment.libclang_path.as_deref(), None);
    assert!(dry_run
        .environment
        .diagnostics
        .iter()
        .any(|diagnostic| { diagnostic.contains("LIBCLANG_PATH is not set") }));
    assert!(dry_run
        .diagnostics
        .contains(&"libclang execution is not enabled in this dry-run skeleton".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_dry_run_records_configured_libclang_path_without_enabling_parse() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
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
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "LIBCLANG_PATH".to_string(),
        "C:/LLVM/bin/libclang.dll".to_string(),
    )]);

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run_with_environment(&environment);

    assert_eq!(dry_run.status, "ready_without_libclang");
    assert_eq!(dry_run.environment.status, "configured");
    assert_eq!(dry_run.environment.source.as_deref(), Some("LIBCLANG_PATH"));
    assert_eq!(
        dry_run.environment.libclang_path.as_deref(),
        Some("C:/LLVM/bin/libclang.dll")
    );
    assert!(dry_run.environment.diagnostics.iter().any(|diagnostic| {
        diagnostic.contains("configured but real libclang parsing remains disabled")
    }));
    assert!(dry_run
        .diagnostics
        .contains(&"libclang execution is not enabled in this dry-run skeleton".to_string()));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_dry_run_prefers_compile_commands_over_synthesized_args() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
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
        "compile_commands": "build/compile_commands.json",
        "build_profile": {
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "compile_commands.json",
            "clang_available": false
        }
    }))
    .unwrap();

    let dry_run = ClangParseSpec::from_slice_spec(&spec)
        .expect("clang parse spec")
        .dry_run();

    assert_eq!(dry_run.arguments, Vec::<String>::new());
    assert_eq!(
        dry_run.compile_commands.as_deref(),
        Some("build/compile_commands.json")
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_missing_source_hash_and_function_span() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must require source file hash coverage");

    assert_eq!(error.kind, "missing_source_file_hash");
    assert_eq!(
        error.to_string(),
        "clang frontend dry-run requires source_file_hashes entry for source_file"
    );
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_function_span_for_a_different_source_file() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/other.c",
            "line_start": 77,
            "line_end": 89,
            "byte_start": 3818,
            "byte_end": 4075,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must bind the span to source_file");

    assert_eq!(error.kind, "function_span_source_file_mismatch");
    assert!(error
        .to_string()
        .contains("function_source_span.file must match source_file"));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_parse_spec_rejects_missing_real_tu_metadata() {
    let spec = SliceSpec {
        target_id: "flashdb".to_string(),
        slice_id: "real-fdb-calc-crc32".to_string(),
        source_commit: "93d1755".to_string(),
        function_name: "fdb_calc_crc32".to_string(),
        c_source:
            "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let error = ClangParseSpec::from_slice_spec(&spec)
        .expect_err("clang frontend must require real TU metadata");

    assert_eq!(error.kind, "missing_source_root");
    assert_eq!(
        error.to_string(),
        "clang frontend dry-run requires source_root"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_builds_typed_ir_for_add_one_fixture() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Add,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty.clone(),
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    assert_eq!(ir.name, "add_one");
    assert!(matches!(
        ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert_eq!(ir.params.len(), 1);
    assert_eq!(ir.params[0].name, "value");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Add,
                lhs,
                rhs,
                ty,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-add statement");
    };
    assert!(matches!(ty.kind, IrTypeKind::Integer { width: 32, .. }));
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_add_one_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "add_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Add,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower add_one skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit add_one from lowered typed IR");

    assert!(rust.contains("pub fn add_one(value: i32) -> i32"));
    assert!(rust.contains("return (value + 1i32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-add-one", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_subtraction_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "sub_one".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Sub,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower sub_one skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Sub,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-sub statement");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Var { name, .. } if name == "value"
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 1, spelling, .. } if spelling == "1"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit sub_one from lowered typed IR");

    assert!(rust.contains("pub fn sub_one(value: i32) -> i32"));
    assert!(rust.contains("return (value - 1i32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-sub-one", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_mul_div_mod_from_clang_lowered_ir() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let mul = ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Mul,
        lhs: Box::new(ClangExprSkeleton::DeclRef {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }),
        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
            value: 3,
            spelling: "3".to_string(),
            ty: int_ty.clone(),
        }),
        ty: int_ty.clone(),
    };
    let div = ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Div,
        lhs: Box::new(mul),
        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
            value: 2,
            spelling: "2".to_string(),
            ty: int_ty.clone(),
        }),
        ty: int_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "mul_div_mod".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Mod,
                lhs: Box::new(div),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 5,
                    spelling: "5".to_string(),
                    ty: int_ty.clone(),
                }),
                ty: int_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower mul_div_mod skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Mod,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected single return-mod statement");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Div,
            ..
        }
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 5, spelling, .. } if spelling == "5"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit mul_div_mod from lowered typed IR");

    assert!(rust.contains("pub fn mul_div_mod(value: i32) -> i32"));
    assert!(rust.contains("return (((value * 3i32) / 2i32) % 5i32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-scalar-mul-div-mod", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_bitxor_bitnot_assignment() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_xor_not".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Assign {
                target: ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                },
                value: ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::BitXor,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::Unary {
                        op: ClangUnaryOperator::BitNot,
                        operand: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 0,
                            spelling: "0".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        ty: uint32_ty.clone(),
                    }),
                    ty: uint32_ty.clone(),
                },
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower bitxor bitnot assignment");

    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!(
            "expected bitxor assignment followed by return, got {:?}",
            ir.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        lhs,
        rhs,
        ..
    } = value
    else {
        panic!("expected bitxor assignment value, got {value:?}");
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand,
        ..
    } = rhs.as_ref()
    else {
        panic!("expected bitnot rhs, got {rhs:?}");
    };
    assert!(
        matches!(operand.as_ref(), IrExpr::LitInt { value: 0, spelling, .. } if spelling == "0")
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_bitand_array_index_expr() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let const_uint32_array_ty = ClangTypeSkeleton {
        spelled: "const uint32_t[256]".to_string(),
        canonical: "uint32_t[256]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(uint32_ty.clone()),
            len: Some(256),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_index".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "idx".to_string(),
                ty: uint32_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "table".to_string(),
                    ty: const_uint32_array_ty,
                }),
                index: Box::new(ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::BitAnd,
                    lhs: Box::new(ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::BitXor,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "crc".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "idx".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        ty: uint32_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                        value: 255,
                        spelling: "255".to_string(),
                        ty: int_ty,
                    }),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower bitand array index");

    let [IrStmt::Return {
        value: Some(IrExpr::Index { index, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return table index, got {:?}", ir.body);
    };
    let IrExpr::Binary {
        op: IrBinOp::BitAnd,
        lhs,
        rhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 255, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_shift_right_expr() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_shift".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Shr,
                lhs: Box::new(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                }),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 8,
                    spelling: "8".to_string(),
                    ty: int_ty,
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower shift right expression");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::Shr,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected shift right return, got {:?}", ir.body);
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(rhs.as_ref(), IrExpr::LitInt { value: 8, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_simple_while_statement() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                },
                body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                    value: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower while statement");

    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", ir.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "crc"));
    let [IrStmt::Assign { target, value, .. }] = body.as_slice() else {
        panic!("expected one while-body assignment, got {body:?}");
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(value, IrExpr::Var { name, .. } if name == "crc"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_while_from_clang_lowered_ir() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                },
                body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::BitXor,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "crc".to_string(),
                            ty: uint32_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::Unary {
                            op: ClangUnaryOperator::BitNot,
                            operand: Box::new(ClangExprSkeleton::IntegerLiteral {
                                value: 0,
                                spelling: "0U".to_string(),
                                ty: uint32_ty.clone(),
                            }),
                            ty: uint32_ty.clone(),
                        }),
                        ty: uint32_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty.clone(),
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower scalar while skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit scalar while from lowered IR");

    assert!(rust.contains("pub fn crc_while(mut crc: u32) -> u32"));
    assert!(rust.contains("while crc != 0u32 {"));
    assert!(rust.contains("crc = (crc ^ !0u32);"));
    assert!(rust.contains("return crc;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-scalar-while", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn clang_scalar_if_skeleton() -> ClangFunctionSkeleton {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    ClangFunctionSkeleton {
        name: "adjust_if".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
            ClangParamSkeleton {
                name: "flag".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::DeclRef {
                    name: "flag".to_string(),
                    ty: int_ty.clone(),
                },
                then_body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "value".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
                else_body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "value".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::Unary {
                            op: ClangUnaryOperator::BitNot,
                            operand: Box::new(ClangExprSkeleton::IntegerLiteral {
                                value: 0,
                                spelling: "0".to_string(),
                                ty: int_ty.clone(),
                            }),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_simple_if_statement() {
    let skeleton = clang_scalar_if_skeleton();

    let ir = lower_function_skeleton(&skeleton).expect("lower if statement");

    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", ir.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_if_without_else_to_empty_else_body() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "adjust_if_no_else".to_string(),
        return_type: int_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "value".to_string(),
                ty: int_ty.clone(),
            },
            ClangParamSkeleton {
                name: "flag".to_string(),
                ty: int_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::DeclRef {
                    name: "flag".to_string(),
                    ty: int_ty.clone(),
                },
                then_body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "value".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
                else_body: vec![],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower if without else");

    let [IrStmt::If { else_body, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected if followed by return, got {:?}", ir.body);
    };
    assert!(
        else_body.is_empty(),
        "expected missing else to lower to empty else body"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_comparison_if_condition() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "adjust_positive".to_string(),
        return_type: int_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: int_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::If {
                condition: ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Gt,
                    lhs: Box::new(ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    }),
                    rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                        value: 0,
                        spelling: "0".to_string(),
                        ty: int_ty.clone(),
                    }),
                    ty: int_ty.clone(),
                },
                then_body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "value".to_string(),
                        ty: int_ty.clone(),
                    },
                    value: ClangExprSkeleton::Binary {
                        op: ClangBinaryOperator::Add,
                        lhs: Box::new(ClangExprSkeleton::DeclRef {
                            name: "value".to_string(),
                            ty: int_ty.clone(),
                        }),
                        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                            value: 1,
                            spelling: "1".to_string(),
                            ty: int_ty.clone(),
                        }),
                        ty: int_ty.clone(),
                    },
                }],
                else_body: vec![],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "value".to_string(),
                    ty: int_ty,
                }),
            },
        ],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower comparison if condition");

    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::Gt, ..
        },
        ..
    }, IrStmt::Return { .. }] = ir.body.as_slice()
    else {
        panic!(
            "expected comparison if followed by return, got {:?}",
            ir.body
        );
    };

    let rust = emit_rust_from_ir(&ir).expect("emit comparison if from lowered IR");
    assert!(rust.contains("if (value > 0i32) {"));
    assert_rust_snippet_compiles("typed-ir-clang-if-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_if_from_clang_lowered_ir() {
    let skeleton = clang_scalar_if_skeleton();
    let ir = lower_function_skeleton(&skeleton).expect("lower scalar if skeleton");

    let rust = emit_rust_from_ir(&ir).expect("emit scalar if from lowered IR");

    assert!(rust.contains("pub fn adjust_if(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = (value + 1i32);"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = (value + !0i32);"));
    assert!(rust.contains("return value;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-clang-scalar-if", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_postfix_decrement_condition() {
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_while_size".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "size".to_string(),
                ty: size_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::While {
                condition: ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "size".to_string(),
                        ty: size_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Dec,
                    prefix: false,
                    ty: size_ty.clone(),
                },
                body: vec![ClangStmtSkeleton::Assign {
                    target: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                    value: ClangExprSkeleton::DeclRef {
                        name: "crc".to_string(),
                        ty: uint32_ty.clone(),
                    },
                }],
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower postfix decrement condition");

    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", ir.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ..
    } = condition
    else {
        panic!("expected postfix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_const_void_pointer_and_size_t_params() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_void_ty = ClangTypeSkeleton {
        spelled: "const void".to_string(),
        canonical: "void".to_string(),
        kind: ClangTypeKind::Void,
    };
    let const_void_ptr_ty = ClangTypeSkeleton {
        spelled: "const void *".to_string(),
        canonical: "void *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_void_ty),
        },
    };
    let size_ty = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_identity".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "buf".to_string(),
                ty: const_void_ptr_ty,
            },
            ClangParamSkeleton {
                name: "size".to_string(),
                ty: size_ty,
            },
        ],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::DeclRef {
                name: "crc".to_string(),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower crc_identity skeleton");

    assert_eq!(ir.params.len(), 3);
    match &ir.params[1].ty.kind {
        IrTypeKind::Pointer { pointee } => {
            assert!(!ir.params[1].ty.is_const);
            assert!(matches!(pointee.kind, IrTypeKind::Void));
            assert!(pointee.is_const);
        }
        other => panic!("expected pointer param, got {other:?}"),
    }
    assert!(matches!(
        ir.params[2].ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
    assert_eq!(ir.params[2].ty.canonical, "size_t");
    assert_eq!(ir.params[2].ty.width_bits, Some(64));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_const_uint8_pointer_decl() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_uint8_ty = ClangTypeSkeleton {
        spelled: "const uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint8_t *".to_string(),
        canonical: "uint8_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint8_ty),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_decl".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "crc".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "p".to_string(),
                ty: const_uint8_ptr_ty,
                init: None,
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower declaration skeleton");

    let [IrStmt::Decl { name, ty, init, .. }, IrStmt::Return { .. }] = ir.body.as_slice() else {
        panic!("expected declaration followed by return, got {:?}", ir.body);
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
fn clang_lowering_skeleton_maps_pointer_cast_assignment() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_void_ty = ClangTypeSkeleton {
        spelled: "const void".to_string(),
        canonical: "void".to_string(),
        kind: ClangTypeKind::Void,
    };
    let const_void_ptr_ty = ClangTypeSkeleton {
        spelled: "const void *".to_string(),
        canonical: "void *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_void_ty),
        },
    };
    let const_uint8_ty = ClangTypeSkeleton {
        spelled: "const uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint8_t *".to_string(),
        canonical: "uint8_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint8_ty),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "crc_assign_ptr".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "crc".to_string(),
                ty: uint32_ty.clone(),
            },
            ClangParamSkeleton {
                name: "buf".to_string(),
                ty: const_void_ptr_ty.clone(),
            },
        ],
        body: vec![
            ClangStmtSkeleton::Decl {
                name: "p".to_string(),
                ty: const_uint8_ptr_ty.clone(),
                init: None,
            },
            ClangStmtSkeleton::Assign {
                target: ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: const_uint8_ptr_ty.clone(),
                },
                value: ClangExprSkeleton::Cast {
                    target: const_uint8_ptr_ty,
                    expr: Box::new(ClangExprSkeleton::DeclRef {
                        name: "buf".to_string(),
                        ty: const_void_ptr_ty,
                    }),
                    implicit: false,
                },
            },
            ClangStmtSkeleton::Return {
                value: Some(ClangExprSkeleton::DeclRef {
                    name: "crc".to_string(),
                    ty: uint32_ty,
                }),
            },
        ],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower pointer cast assignment");

    let [IrStmt::Decl { .. }, IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] =
        ir.body.as_slice()
    else {
        panic!(
            "expected declaration, pointer cast assignment, return; got {:?}",
            ir.body
        );
    };
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
fn clang_lowering_skeleton_maps_pointer_deref_expr() {
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ty = ClangTypeSkeleton {
        spelled: "const uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint8_t *".to_string(),
        canonical: "uint8_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint8_ty),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "read_byte".to_string(),
        return_type: uint8_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: const_uint8_ptr_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::DeclRef {
                    name: "p".to_string(),
                    ty: const_uint8_ptr_ty,
                }),
                ty: uint8_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower pointer deref skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, ty, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return deref, got {:?}", ir.body);
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
fn clang_lowering_skeleton_maps_postfix_increment_in_deref_expr() {
    let uint8_ty = ClangTypeSkeleton {
        spelled: "uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ty = ClangTypeSkeleton {
        spelled: "const uint8_t".to_string(),
        canonical: "uint8_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    };
    let const_uint8_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint8_t *".to_string(),
        canonical: "uint8_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint8_ty),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "read_byte_inc".to_string(),
        return_type: uint8_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "p".to_string(),
            ty: const_uint8_ptr_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Deref {
                ptr: Box::new(ClangExprSkeleton::IncDec {
                    target: Box::new(ClangExprSkeleton::DeclRef {
                        name: "p".to_string(),
                        ty: const_uint8_ptr_ty.clone(),
                    }),
                    op: ClangIncDecOperator::Inc,
                    prefix: false,
                    ty: const_uint8_ptr_ty,
                }),
                ty: uint8_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower postfix increment in deref skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Deref { ptr, ty, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return deref, got {:?}", ir.body);
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
fn clang_lowering_skeleton_maps_array_subscript_expr() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_uint32_ty = ClangTypeSkeleton {
        spelled: "const uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_uint32_ptr_ty = ClangTypeSkeleton {
        spelled: "const uint32_t *".to_string(),
        canonical: "uint32_t *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(const_uint32_ty),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "read_table".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![
            ClangParamSkeleton {
                name: "table".to_string(),
                ty: const_uint32_ptr_ty.clone(),
            },
            ClangParamSkeleton {
                name: "idx".to_string(),
                ty: uint32_ty.clone(),
            },
        ],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "table".to_string(),
                    ty: const_uint32_ptr_ty,
                }),
                index: Box::new(ClangExprSkeleton::DeclRef {
                    name: "idx".to_string(),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower array subscript skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Index {
            base, index, ty, ..
        }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return table index, got {:?}", ir.body);
    };
    assert!(matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "table"));
    assert!(matches!(index.as_ref(), IrExpr::Var { name, .. } if name == "idx"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_lowering_skeleton_maps_const_array_type() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let const_uint32_array_ty = ClangTypeSkeleton {
        spelled: "const uint32_t[256]".to_string(),
        canonical: "uint32_t[256]".to_string(),
        kind: ClangTypeKind::Array {
            element: Box::new(uint32_ty.clone()),
            len: Some(256),
        },
    };
    let skeleton = ClangFunctionSkeleton {
        name: "read_table".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "idx".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Index {
                base: Box::new(ClangExprSkeleton::DeclRef {
                    name: "table".to_string(),
                    ty: const_uint32_array_ty,
                }),
                index: Box::new(ClangExprSkeleton::DeclRef {
                    name: "idx".to_string(),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };

    let ir = lower_function_skeleton(&skeleton).expect("lower const array skeleton");

    let [IrStmt::Return {
        value: Some(IrExpr::Index { base, .. }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected return table index, got {:?}", ir.body);
    };
    let IrExpr::Var { ty, .. } = base.as_ref() else {
        panic!("expected array base variable, got {base:?}");
    };
    assert!(ty.is_const);
    match &ty.kind {
        IrTypeKind::Array { element, len } => {
            assert_eq!(*len, Some(256));
            assert!(matches!(
                element.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ));
        }
        other => panic!("expected array base type, got {other:?}"),
    }
}

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
fn clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
            "C:/Program Files/LLVM/bin/libclang.dll".to_string(),
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
fn clang_ast_dump_emits_real_scalar_subtraction_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
    assert!(rust.contains("return (value - 1i32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-scalar-subtraction", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_real_scalar_mul_div_mod_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
    assert!(rust.contains("return (((value * 3i32) / 2i32) % 5i32);"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-scalar-mul-div-mod", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_parse_spec_report_uses_include_paths_for_real_ast_dump_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_uint32_integer_type_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_const_void_pointer_and_size_t_params_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_const_uint8_pointer_decl_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_assignment_statement_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_pointer_cast_assignment_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_pointer_deref_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_postfix_increment_deref_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_deref_in_bitand_array_index_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_postfix_increment_deref_in_bitand_array_index_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_shift_right_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_crc_update_expr_with_postinc_and_shift_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-crc-update-postinc-shift");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_update_expr.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_update_expr(uint32_t crc, const uint8_t *p) { return table[(crc ^ *p++) & 0xff] ^ (crc >> 8); }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_update_expr");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::BitXor,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected crc update return, got {:?}", function.body);
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Index { .. }));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Shr,
            ..
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_const_pointer_table_index_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-const-pointer-table-index-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t read_table(const uint32_t *table, uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit const pointer table index");
    assert!(rust.contains("pub fn read_table(table: &[u32], idx: u32) -> u32"));
    assert!(rust.contains("return table[idx as usize];"));
    assert_rust_snippet_compiles("typed-ir-real-clang-const-pointer-table-index", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_const_void_byte_cursor_read_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-const-void-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_from_void.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_from_void(const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return *p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "read_byte_from_void",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit const void byte cursor read");
    assert!(rust.contains("pub fn read_byte_from_void(buf: &[u8]) -> u8"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return byte0;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-const-void-byte-cursor-read", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_nested_const_void_byte_cursor_read_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-nested-const-void-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_byte.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_byte(uint32_t crc, const void *buf) { const uint8_t *p; p = (const uint8_t *)buf; return crc ^ (uint32_t)*p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_byte");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit nested const void byte cursor read");
    assert!(rust.contains("pub fn crc_xor_byte(crc: u32, buf: &[u8]) -> u32"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-const-void-byte-cursor-read",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_nested_const_u8_byte_cursor_read_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-nested-const-u8-byte-cursor-read-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_byte_from_u8.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_byte_from_u8(uint32_t crc, const uint8_t *p) { return crc ^ (uint32_t)*p++; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "crc_xor_byte_from_u8",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit nested const u8 byte cursor read");
    assert!(rust.contains("pub fn crc_xor_byte_from_u8(crc: u32, p: &[u8]) -> u32"));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(rust.contains("return (crc ^ (byte0 as u32));"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-nested-const-u8-byte-cursor-read",
        &rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_crc_update_assignment_with_pointer_table_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-crc-update-assignment-pointer-table-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("update_crc_step_from_clang.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t update_crc_step_from_clang(uint32_t crc, const uint8_t *p, const uint32_t *table) { crc = table[(crc ^ (uint32_t)*p++) & 0xffU] ^ (crc >> 8U); return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "update_crc_step_from_clang",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted =
        emit_rust_from_ir(function).expect("emit clang crc update assignment with pointer table");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains(
        "pub fn update_crc_step_from_clang(mut crc: u32, p: &[u8], table: &[u32]) -> u32"
    ));
    assert!(rust.contains("let mut p_index: usize = 0;"));
    assert!(rust.contains("let byte0: u8 = p[p_index];"));
    assert!(rust.contains("p_index += 1;"));
    assert!(
        rust.contains("crc = (table[((crc ^ (byte0 as u32)) & 255u32) as usize] ^ (crc >> 8u32));")
    );
    assert!(rust.contains("return crc;"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles(
        "typed-ir-real-clang-crc-update-assignment-pointer-table",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_flashdb_crc32_from_lowered_ir_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-flashdb-crc32-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("fdb_utils.c");
    let table_values = repeated_c_u32_initializer(256, "0U");
    fs::write(
        &source_file,
        format!(
            "#include <stdint.h>\n#include <stddef.h>\nstatic const uint32_t crc32_table[256] = {{ {table_values} }};\nuint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) {{\n    const uint8_t *p;\n    p = (const uint8_t *)buf;\n    crc = crc ^ ~0U;\n    while (size--) {{\n        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);\n    }}\n    return crc ^ ~0U;\n}}\n"
        ),
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "fdb_calc_crc32");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert_eq!(report.globals.len(), 1);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit rust from real clang-lowered crc32 ir");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 0u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ (crc >> 8"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-clang-flashdb-crc32-generic", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_parse_spec_emits_real_flashdb_crc32_from_lowered_ir_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let real_spec_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../validation/slice-specs/flashdb-real-fdb-calc-crc32.json");
    let real_spec: Value = serde_json::from_str(
        &fs::read_to_string(&real_spec_path).expect("read real fdb slice spec"),
    )
    .expect("parse real fdb slice spec");
    let source_file = "src/fdb_utils.c";
    let function_source_span = serde_json::from_value(
        real_spec
            .pointer("/c_boundary/signatures/0/source_span")
            .expect("function source span")
            .clone(),
    )
    .expect("parse function source span");
    let spec = SliceSpec {
        target_id: real_spec["target_id"].as_str().unwrap().to_string(),
        slice_id: real_spec["slice_id"].as_str().unwrap().to_string(),
        source_commit: real_spec["source_commit"].as_str().unwrap().to_string(),
        function_name: real_spec["function_name"].as_str().unwrap().to_string(),
        c_source: real_spec["c_source"].as_str().unwrap().to_string(),
        fixture_hash: real_spec["fixture_hash"].as_str().unwrap().to_string(),
        source_root: Some(
            real_spec["source"]["source_root"]
                .as_str()
                .unwrap()
                .to_string(),
        ),
        source_file: Some(source_file.to_string()),
        source_file_hashes: std::collections::BTreeMap::from([(
            source_file.to_string(),
            real_spec["source"]["source_file_hashes"][source_file]
                .as_str()
                .unwrap()
                .to_string(),
        )]),
        function_source_span: Some(function_source_span),
        build_profile: BuildProfile {
            include_paths: vec!["inc".to_string(), "tests".to_string()],
            defines: Vec::new(),
            target_triple: None,
            abi: None,
            compiler_command_source: "real-flashdb-slice-spec-test".to_string(),
            clang_available: true,
        },
        ..SliceSpec::default()
    };
    let parse_spec = ClangParseSpec::from_slice_spec(&spec).expect("clang parse spec");
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_parse_spec_report(&environment, &parse_spec);

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.errors.is_empty(), "{:?}", report.errors);
    assert!(report.globals.iter().any(|global| {
        global.name == "crc32_table"
            && matches!(global.ty.kind, IrTypeKind::Array { len: Some(256), .. })
    }));
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit rust from real fdb clang-lowered ir");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 1996959894u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ (crc >> 8"));
    assert!(!rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("typed-ir-real-flashdb-crc32-generic", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_array_subscript_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-array-subscript");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t read_table(const uint32_t *table, uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index {
            base, index, ty, ..
        }),
        ..
    }] = function.body.as_slice()
    else {
        panic!("expected array subscript return, got {:?}", function.body);
    };
    assert!(matches!(base.as_ref(), IrExpr::Var { name, .. } if name == "table"));
    assert!(matches!(index.as_ref(), IrExpr::Var { name, .. } if name == "idx"));
    assert!(matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_global_const_array_subscript_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-global-array-subscript");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Return {
        value: Some(IrExpr::Index { base, .. }),
        ..
    }] = function.body.as_slice()
    else {
        panic!(
            "expected global array subscript return, got {:?}",
            function.body
        );
    };
    let IrExpr::Var { name, ty, .. } = base.as_ref() else {
        panic!("expected table variable, got {base:?}");
    };
    assert_eq!(name, "table");
    assert!(ty.is_const);
    assert!(matches!(ty.kind, IrTypeKind::Array { len: Some(256), .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_records_static_const_integer_array_global_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-global-array-initializer");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table_init.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[4] = { 1U, 2U, 0xEDB88320U, 4U };\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert_eq!(report.globals.len(), 1);
    let global = &report.globals[0];
    assert_eq!(global.name, "table");
    assert!(global.ty.is_const);
    assert!(matches!(
        global.ty.kind,
        IrTypeKind::Array { len: Some(4), .. }
    ));
    assert_eq!(
        global.init,
        IrGlobalInit::IntegerArray(vec![1, 2, 0xEDB8_8320, 4])
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_static_const_integer_array_global_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-global-array-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_global_table_emit.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[4] = { 1U, 2U, 0xEDB88320U, 4U };\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let emitted = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect("emit global table from clang typed IR");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(!emitted.route.deprecated);
    assert!(emitted
        .rust
        .contains("const TABLE: [u32; 4] = [1u32, 2u32, 3988292384u32, 4u32];"));
    assert!(emitted
        .rust
        .contains("pub fn read_global_table(idx: u32) -> u32"));
    assert!(emitted.rust.contains("return TABLE[idx as usize];"));
    assert!(!emitted.rust.contains("crc32_update_byte"));
    assert_rust_snippet_compiles("clang_real_global_array_emit", &emitted.rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_records_static_const_incomplete_array_initializer_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-incomplete-global-array-init");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_incomplete_global_table_init.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[] = { 1U, 2U, 0xEDB88320U, 4U };\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert_eq!(report.globals.len(), 1);
    let global = &report.globals[0];
    assert_eq!(global.name, "table");
    assert!(matches!(
        global.ty.kind,
        IrTypeKind::Array { len: Some(4), .. }
    ));
    assert_eq!(
        global.init,
        IrGlobalInit::IntegerArray(vec![1, 2, 0xEDB8_8320, 4])
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_does_not_synthesize_uninitialized_static_const_global_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-uninitialized-global-array");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_uninitialized_global_table.c");
    fs::write(
        &source_file,
        "typedef unsigned int uint32_t;\nstatic const uint32_t table[4];\nuint32_t read_global_table(uint32_t idx) { return table[idx]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "read_global_table");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    assert!(report.globals.is_empty());
    let function = report.function_ir.as_ref().expect("function ir");
    let error = emit_rust_from_ir_with_globals(function, &report.globals)
        .expect_err("uninitialized global table must not be synthesized");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("index base table is not declared"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_bitand_array_index_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-bitand-array-index");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_index.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nstatic const uint32_t table[256];\nuint32_t crc_index(uint32_t crc, uint32_t idx) { return table[(crc ^ idx) & 0xff]; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_index");

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
        rhs,
        ..
    } = index.as_ref()
    else {
        panic!("expected bitand index expression, got {index:?}");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
    assert!(matches!(
        without_implicit_cast(rhs.as_ref()),
        IrExpr::LitInt { value: 255, .. }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_bitxor_bitnot_assignment_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-bitxor-bitnot-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_not.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_not(uint32_t crc) { crc = crc ^ ~0U; return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_not");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { target, value, .. }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected bitxor assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(target, IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Binary {
        op: IrBinOp::BitXor,
        lhs,
        rhs,
        ..
    } = value
    else {
        panic!("expected bitxor assignment value, got {value:?}");
    };
    assert!(matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "crc"));
    let IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand,
        ..
    } = rhs.as_ref()
    else {
        panic!("expected bitnot rhs, got {rhs:?}");
    };
    assert!(matches!(operand.as_ref(), IrExpr::LitInt { value: 0, .. }));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_parenthesized_bitxor_bitnot_assignment_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-parenthesized-bitxor-bitnot-assignment");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_xor_not_paren.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_xor_not_paren(uint32_t crc) { crc = (crc ^ ~0U); return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_xor_not_paren");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::Assign { value, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!(
            "expected parenthesized bitxor assignment followed by return, got {:?}",
            function.body
        );
    };
    assert!(matches!(
        value,
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            ..
        }
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_simple_while_statement_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-simple-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t crc_while(uint32_t crc) { while (crc) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_while");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "crc"));
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "crc")
                && matches!(value, IrExpr::Var { name, .. } if name == "crc")
    ));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_while_without_braces_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-while-without-braces");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("countdown_no_braces.c");
    fs::write(
        &source_file,
        "int countdown_no_braces(int value) { while (value > 0) value = value + ~0; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "countdown_no_braces",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While {
        condition, body, ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::Gt,
            ..
        }
    ));
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit no-brace while from real clang AST");
    assert!(rust.contains("pub fn countdown_no_braces(mut value: i32) -> i32"));
    assert!(rust.contains("while (value > 0i32) {"));
    assert!(rust.contains("value = (value + !0i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-while-without-braces", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_simple_if_statement_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-simple-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_if.c");
    fs::write(
        &source_file,
        "int adjust_if(int value, int flag) { if (flag) { value = value + 1; } else { value = value + ~0; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "adjust_if");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit simple if from real clang AST");
    assert!(rust.contains("pub fn adjust_if(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = (value + 1i32);"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = (value + !0i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_if_without_braces_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-if-without-braces");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_if_no_braces.c");
    fs::write(
        &source_file,
        "int adjust_if_no_braces(int value, int flag) { if (flag) value = value + 1; else value = value + ~0; return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "adjust_if_no_braces",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!("expected if followed by return, got {:?}", function.body);
    };
    assert!(matches!(condition, IrExpr::Var { name, .. } if name == "flag"));
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign { value, .. }] if matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));
    assert!(matches!(
        else_body.as_slice(),
        [IrStmt::Assign { value, .. }] if matches!(value, IrExpr::Binary { op: IrBinOp::Add, .. })
    ));

    let rust = emit_rust_from_ir(function).expect("emit no-brace if from real clang AST");
    assert!(rust.contains("pub fn adjust_if_no_braces(mut value: i32, flag: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("value = (value + 1i32);"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("value = (value + !0i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-without-braces", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_comparison_if_condition_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-comparison-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_positive.c");
    fs::write(
        &source_file,
        "int adjust_positive(int value) { if (value > 0) { value = value + 1; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "adjust_positive");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition: IrExpr::Binary {
            op: IrBinOp::Gt, ..
        },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected comparison if followed by return, got {:?}",
            function.body
        );
    };

    let rust = emit_rust_from_ir(function).expect("emit comparison if from real clang AST");
    assert!(rust.contains("pub fn adjust_positive(mut value: i32) -> i32"));
    assert!(rust.contains("if (value > 0i32) {"));
    assert!(rust.contains("value = (value + 1i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_unsigned_comparison_if_condition_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-unsigned-comparison-if");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("adjust_unsigned_positive.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint32_t adjust_unsigned_positive(uint32_t value) { if (value > 0) { value = value + 1U; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "adjust_unsigned_positive",
    );

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::If {
        condition:
            IrExpr::Binary {
                op: IrBinOp::Gt,
                rhs,
                ..
            },
        ..
    }, IrStmt::Return { .. }] = function.body.as_slice()
    else {
        panic!(
            "expected unsigned comparison if followed by return, got {:?}",
            function.body
        );
    };
    assert!(
        matches!(rhs.as_ref(), IrExpr::Cast { implicit: true, .. }),
        "expected clang integral cast on unsigned comparison literal, got {rhs:?}"
    );

    let rust =
        emit_rust_from_ir(function).expect("emit unsigned comparison if from real clang AST");
    assert!(rust.contains("pub fn adjust_unsigned_positive(mut value: u32) -> u32"));
    assert!(rust.contains("if (value > (0i32 as u32)) {"));
    assert!(rust.contains("value = (value + 1u32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-if-unsigned-comparison", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_rejects_postfix_increment_if_condition_in_scalar_emitter_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-postfix-increment-if-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_if_postinc.c");
    fs::write(
        &source_file,
        "int bad_if_postinc(int value) { if (value++) { value = value; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_if_postinc");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let error =
        emit_rust_from_ir(function).expect_err("postfix increment if condition must fail closed");
    assert!(error.reason.contains("stmt[0].if condition"));
    assert!(error.reason.contains("inc/dec expression is unsupported"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_lowers_postfix_decrement_while_condition_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-postfix-decrement-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while_size.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t crc_while_size(uint32_t crc, size_t size) { while (size--) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "crc_while_size");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let [IrStmt::While { condition, .. }, IrStmt::Return { .. }] = function.body.as_slice() else {
        panic!("expected while followed by return, got {:?}", function.body);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ..
    } = condition
    else {
        panic!("expected postfix decrement condition, got {condition:?}");
    };
    assert!(matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "size"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_postfix_decrement_while_condition_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-postfix-decrement-while-emit");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("bad_while_size.c");
    fs::write(
        &source_file,
        "#include <stddef.h>\nint bad_while_size(int value, size_t size) { while (size--) { value = value; } return value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "bad_while_size");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit postfix decrement while condition");
    assert!(rust.contains("pub fn bad_while_size(mut value: i32, mut size: usize) -> i32"));
    assert!(rust.contains("loop {"));
    assert!(rust.contains("let size_before_dec0: usize = size;"));
    assert!(rust.contains("size = size.wrapping_sub(1usize);"));
    assert!(rust.contains("if size_before_dec0 == 0usize {"));
    assert!(rust.contains("break;"));
    assert!(rust.contains("value = value;"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-real-clang-postfix-decrement-while", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_rejects_prefix_decrement_while_condition_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-prefix-decrement-while");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("crc_while_prefix_size.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\n#include <stddef.h>\nuint32_t crc_while_prefix_size(uint32_t crc, size_t size) { while (--size) { crc = crc; } return crc; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "crc_while_prefix_size",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert_eq!(
        report.errors.first().map(|error| error.kind.as_str()),
        Some("unsupported_clang_expr")
    );
    assert!(
        report
            .errors
            .first()
            .map(|error| error.message.contains("prefix opcode --"))
            .unwrap_or(false),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_rejects_prefix_increment_deref_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-prefix-increment-deref");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("read_byte_prefix_inc.c");
    fs::write(
        &source_file,
        "#include <stdint.h>\nuint8_t read_byte_prefix_inc(const uint8_t *p) { return *++p; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "read_byte_prefix_inc",
    );

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert_eq!(
        report.errors.first().map(|error| error.kind.as_str()),
        Some("unsupported_clang_expr")
    );
    assert!(
        report
            .errors
            .first()
            .map(|error| error.message.contains("prefix opcode ++"))
            .unwrap_or(false),
        "{:?}",
        report.errors
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_integral_c_style_cast_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-integral-cast");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("narrow.c");
    fs::write(
        &source_file,
        "unsigned int narrow(unsigned long value) { return (unsigned int)value; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(&environment, &source_file, "narrow");

    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("function ir");
    let rust = emit_rust_from_ir(function).expect("emit integral C-style cast");
    assert!(rust.contains("pub fn narrow(value: u64) -> u32"));
    assert!(rust.contains("return (value as u32);"));
    assert_rust_snippet_compiles("typed-ir-real-clang-integral-c-style-cast", &rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_dump_emits_initialized_decl_stmt_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_emits_local_fixed_array_initializer_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_emits_local_fixed_array_index_assignment_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_rejects_local_array_initializer_call_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_lowers_initialized_decl_with_direct_call_expr_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
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
fn clang_ast_dump_rejects_multi_var_decl_stmt_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let out_dir = unique_out_dir("clang-real-multi-var-decl-reject");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("multi_decl.c");
    fs::write(
        &source_file,
        "int multi_decl(void) { int a = 1, b = 2; return a + b; }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report =
        lower_function_from_clang_ast_dump_report(&environment, &source_file, "multi_decl");

    assert_eq!(report.status, "unsupported", "{:?}", report.errors);
    assert_eq!(
        report.errors.first().map(|error| error.kind.as_str()),
        Some("unsupported_clang_stmt")
    );
    assert!(
        report
            .errors
            .first()
            .map(|error| error.message.contains("DeclStmt with 2 VarDecl children"))
            .unwrap_or(false),
        "{:?}",
        report.errors
    );
}

#[test]
fn translates_structured_integer_function_and_emits_type_map_and_cfg() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "add-one".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "add_one".to_string(),
        c_source: "int add_one(int value) { return value + 1; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn add_one(value: i32) -> i32"));
    assert!(result.rust_code.contains("value + 1"));
    assert_eq!(result.type_map.mappings[0].c_type, "int");
    assert_eq!(result.type_map.mappings[0].rust_type, "i32");
    assert_eq!(result.cfg.functions[0].name, "add_one");
    assert_eq!(result.cfg.functions[0].blocks[0].terminator, "return");
    assert!(result.pointer_graph.nodes.is_empty());
    assert_eq!(result.plan.unsupported_node_count, 0);
}

#[test]
fn pointer_out_param_generates_safe_public_boundary_and_pointer_graph() {
    let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn uv_ip4_addr(ip: &str, port: i32)"));
    assert!(!result.rust_code.contains("*mut sockaddr_in"));
    assert_eq!(result.pointer_graph.nodes.len(), 2);
    assert!(result
        .pointer_graph
        .nodes
        .iter()
        .any(|node| node.id == "ip" && node.role == "borrowed_input"));
    assert!(result
        .pointer_graph
        .nodes
        .iter()
        .any(|node| node.id == "addr" && node.role == "out_param"));
    let addr = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "addr")
        .expect("addr pointer node");
    assert!(addr.write_effects.contains(&"addr->sin_family".to_string()));
    assert!(addr
        .read_effects
        .contains(&"addr->sin_family = AF_INET".to_string()));
    assert_eq!(result.plan.unsafe_candidate_count, 0);
}

#[test]
fn pointer_field_writes_record_lvalue_and_boundary_decisions() {
    let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr-fields".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; addr->sin_port = port; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("ip4-addr-fields");

    let result = translate_slice(&spec);
    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert_eq!(manifest.slice_id, "ip4-addr-fields");
    let addr = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "addr")
        .expect("addr pointer node");
    assert!(addr.write_effects.contains(&"addr->sin_family".to_string()));
    assert!(addr.write_effects.contains(&"addr->sin_port".to_string()));

    let cfg = json_file(out_dir.join("l3-ip4-addr-fields-cfg.json"));
    let pointer_graph = json_file(out_dir.join("l3-ip4-addr-fields-pointer-graph.json"));
    let plan = json_file(out_dir.join("l3-ip4-addr-fields-auto-translation-plan.json"));
    let lvalue_kinds = cfg["cfg"]["functions"][0]["blocks"][0]["lvalue_kinds"]
        .as_array()
        .expect("lvalue kinds");
    let addr_decisions = pointer_graph["pointer_graph"]["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|node| node["id"] == "addr")
        .and_then(|node| node["boundary_decisions"].as_array())
        .expect("addr boundary decisions");

    assert!(lvalue_kinds.iter().any(|kind| kind == "pointer_field"));
    assert!(addr_decisions
        .iter()
        .any(|decision| decision == "safe_wrapper_candidate"));
    assert!(plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .iter()
        .any(|rule| rule == "pointer-field-write"));
}

#[test]
fn bounded_pointer_index_write_generates_safe_boundary_and_decision() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "fill-first".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "fill_first".to_string(),
        c_source: "int fill_first(int* out, int value) { out[0] = value; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result.rust_code.contains("pub fn fill_first(value: i32)"));
    assert!(!result.rust_code.contains("*mut"));
    let out = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "out")
        .expect("out pointer node");
    assert_eq!(out.role, "out_param");
    assert!(out.write_effects.contains(&"out[0]".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-pointer-index-write".to_string()));
}

#[test]
fn bounded_pointer_index_compound_assignment_records_decision() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "add-first".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "add_first".to_string(),
        c_source: "int add_first(int* out, int value) { out[0] += value; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    let out = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "out")
        .expect("out pointer node");
    assert!(out.write_effects.contains(&"out[0]".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-pointer-index-write".to_string()));
}

#[test]
fn bounded_input_buffer_read_generates_safe_slice_boundary_and_decisions() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-i32-buffer".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_i32_buffer".to_string(),
        c_source: "int sum_i32_buffer(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + values[i]; } out[0] = total; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn sum_i32_buffer(values: &[i32], len: i32)"));
    assert!(result
        .rust_code
        .contains("total = total + values[i as usize];"));
    assert!(!result.rust_code.contains("*const"));
    assert!(!result.rust_code.contains("*mut"));
    let values = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "values")
        .expect("values pointer node");
    assert_eq!(values.role, "borrowed_input");
    assert!(values.read_effects.contains(&"values[i]".to_string()));
    assert!(values
        .boundary_decisions
        .contains(&"bounded_input_buffer".to_string()));
    let out = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "out")
        .expect("out pointer node");
    assert_eq!(out.role, "out_param");
    assert!(out.write_effects.contains(&"out[0]".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-input-buffer-read".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-pointer-index-write".to_string()));
}

#[test]
fn bounded_pointer_arithmetic_read_generates_safe_slice_boundary_and_decisions() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-i32-ptr-arith".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_i32_ptr_arith".to_string(),
        c_source: "int sum_i32_ptr_arith(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + *(values + i); } out[0] = total; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn sum_i32_ptr_arith(values: &[i32], len: i32)"));
    assert!(result
        .rust_code
        .contains("total = total + values[i as usize];"));
    assert!(!result.rust_code.contains("*(values + i)"));
    assert!(!result.rust_code.contains("*const"));
    assert!(!result.rust_code.contains("*mut"));
    let values = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "values")
        .expect("values pointer node");
    assert_eq!(values.role, "borrowed_input");
    assert!(values.read_effects.contains(&"values[i]".to_string()));
    assert!(values.read_effects.contains(&"*(values + i)".to_string()));
    assert!(values
        .boundary_decisions
        .contains(&"bounded_input_buffer".to_string()));
    assert!(values
        .boundary_decisions
        .contains(&"bounded_pointer_arithmetic_input_read".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-input-buffer-read".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
}

#[test]
fn flashdb_crc32_byte_cursor_loop_blocks_without_legacy_canned_template() {
    let spec = SliceSpec {
        target_id: "flashdb".to_string(),
        slice_id: "real-fdb-calc-crc32".to_string(),
        source_commit: "93d1755".to_string(),
        function_name: "fdb_calc_crc32".to_string(),
        c_source: "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size)
{
    const uint8_t *p;

    p = (const uint8_t *)buf;
    crc = crc ^ ~0U;

    while (size--) {
        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
    }

    return crc ^ ~0U;
}"
        .to_string(),
        fixture_hash: "real-fdb-calc-crc32-fixture".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(!result.rust_code.contains("crc32_update_byte"));
    assert!(!result
        .plan
        .translation_rule_ids
        .contains(&"crc32-byte-cursor-loop".to_string()));
    assert!(
        result
            .errors
            .iter()
            .any(|error| error.kind == "unsupported_syntax"),
        "{:?}",
        result.errors
    );
    assert!(result
        .errors
        .iter()
        .any(|error| error.message.contains("increment/decrement")));
}

#[test]
fn bounded_pointer_arithmetic_output_write_generates_safe_mut_slice_boundary_and_decisions() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "fill-i32-ptr-arith-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "fill_i32_ptr_arith_out".to_string(),
        c_source: "int fill_i32_ptr_arith_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn fill_i32_ptr_arith_out(out: &mut [i32], len: i32, value: i32)"));
    assert!(result.rust_code.contains("out[i as usize] = value;"));
    assert!(!result.rust_code.contains("*(out + i)"));
    assert!(!result.rust_code.contains("*mut"));
    let out = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "out")
        .expect("out pointer node");
    assert_eq!(out.role, "out_param");
    assert_eq!(out.rust_boundary, "&mut [i32]");
    assert!(out.write_effects.contains(&"out[i]".to_string()));
    assert!(out.write_effects.contains(&"*(out + i)".to_string()));
    assert!(out
        .boundary_decisions
        .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
    assert!(result.cfg.functions[0].blocks[0]
        .lvalue_kinds
        .contains(&"bounded_pointer_arithmetic_output_buffer".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-pointer-arithmetic-output-write".to_string()));
    assert!(!result
        .plan
        .translation_rule_ids
        .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
}

#[test]
fn unproven_input_buffer_read_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-buffer-read".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_buffer_read".to_string(),
        c_source: "int bad_buffer_read(const int* values, int i, int* out) { out[0] = values[i]; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(
        result
            .errors
            .iter()
            .any(|error| error.kind == "unsupported_syntax"),
        "{:?}",
        result.errors
    );
}

#[test]
fn unproven_pointer_arithmetic_read_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-read".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_read".to_string(),
        c_source: "int bad_ptr_arith_read(const int* values, int i, int* out) { out[0] = *(values + i); return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(
        result
            .errors
            .iter()
            .any(|error| error.kind == "unsupported_syntax"),
        "{:?}",
        result.errors
    );
}

#[test]
fn unproven_pointer_arithmetic_output_write_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_out".to_string(),
        c_source:
            "int bad_ptr_arith_out(int* out, int i, int value) { *(out + i) = value; return 0; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(
        result
            .errors
            .iter()
            .any(|error| error.kind == "unsupported_syntax"),
        "{:?}",
        result.errors
    );
}

#[test]
fn complex_pointer_arithmetic_output_write_blocks_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "bad-ptr-arith-complex-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "bad_ptr_arith_complex_out".to_string(),
        c_source: "int bad_ptr_arith_complex_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i + 1) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(
        result
            .errors
            .iter()
            .any(|error| error.kind == "unsupported_lvalue"),
        "{:?}",
        result.errors
    );
}

#[test]
fn bounded_pointer_arithmetic_writes_do_not_count_as_input_buffer_reads() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "ptr-arith-write".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "ptr_arith_write".to_string(),
        c_source: "int ptr_arith_write(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(!result
        .cfg
        .functions
        .iter()
        .flat_map(|function| function.blocks.iter())
        .flat_map(|block| block.statement_kinds.iter())
        .any(|kind| kind == "bounded_input_buffer_read"));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
    assert!(!result
        .plan
        .translation_rule_ids
        .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
}

#[test]
fn unsupported_complex_lvalues_block_without_false_success() {
    for (slice_id, function_name, c_source) in [
        (
            "unbounded-index",
            "unbounded_index",
            "int unbounded_index(int* out, int i, int value) { out[i] = value; return 0; }",
        ),
        (
            "field-assignment",
            "field_assignment",
            "int field_assignment(int value) { state.field = value; return value; }",
        ),
        (
            "pointer-arithmetic-complex",
            "pointer_arithmetic_complex",
            "int pointer_arithmetic_complex(int* out, int i, int value) { *(out + i + 1) = value; return 0; }",
        ),
    ] {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: slice_id.to_string(),
            source_commit: "1234567".to_string(),
            function_name: function_name.to_string(),
            c_source: c_source.to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.rust_code.is_empty(), "{slice_id}");
        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_lvalue"),
            "{slice_id}: {:?}",
            result.errors
        );
    }
}

#[test]
fn blocks_pointer_out_param_without_observable_write() {
    let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr-no-write".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source:
            "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { return 0; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_pointer_pattern"));
}

#[test]
fn translates_primitive_declaration_assignment_and_return() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "local-state".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "local_state".to_string(),
        c_source:
            "int local_state(int value) { int total = value + 1; total = total + 2; return total; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result.rust_code.contains("let mut total: i32 = value + 1;"));
    assert!(result.rust_code.contains("total = total + 2;"));
    assert!(result.rust_code.contains("return total;"));
    assert!(result.type_map.mappings.iter().any(|mapping| {
        mapping.symbol == "total" && mapping.c_type == "int" && mapping.rust_type == "i32"
    }));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"primitive_declaration".to_string()));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"assignment".to_string()));
}

#[test]
fn blocks_unsupported_local_declaration_type_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "unknown-local".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "unknown_local".to_string(),
        c_source: "int unknown_local(int value) { alias_t local = value; return value; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_syntax"));
}

#[test]
fn translates_if_else_with_cfg_branch_edges() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "clamp".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "clamp_non_negative".to_string(),
        c_source: "int clamp_non_negative(int value) { if (value < 0) { return 0; } else { return value; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result.rust_code.contains("if value < 0 {"));
    assert!(result.rust_code.contains("} else {"));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"if".to_string()));
    assert!(result.cfg.functions[0].blocks[0]
        .edges
        .iter()
        .any(|edge| edge.starts_with("entry->if-")));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"structured-if".to_string()));
}

#[test]
fn translates_while_loop_with_cfg_back_edge() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-while".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_while".to_string(),
        c_source: "int sum_while(int limit) { int total = 0; while (limit > 0) { total = total + limit; limit = limit - 1; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result.rust_code.contains("while limit > 0 {"));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"while".to_string()));
    assert!(result.cfg.functions[0].blocks[0]
        .edges
        .iter()
        .any(|edge| edge.starts_with("entry->while-")));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"structured-while".to_string()));
}

#[test]
fn translates_for_loop_by_lowering_to_bounded_while() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-for".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_for".to_string(),
        c_source: "int sum_for(int limit) { int total = 0; for (int i = 0; i < limit; i++) { total = total + i; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result.rust_code.contains("let mut i: i32 = 0;"));
    assert!(result.rust_code.contains("while i < limit {"));
    assert!(result.rust_code.contains("i += 1;"));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"for".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"structured-for".to_string()));
}

#[test]
fn translates_for_loop_with_compound_assignment_step() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-for-compound-step".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_for_compound_step".to_string(),
        c_source: "int sum_for_compound_step(int limit) { int total = 0; for (int i = 0; i < limit; i += 1) { total = total + i; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result.rust_code.contains("while i < limit {"));
    assert!(result.rust_code.contains("i += 1;"));
}

#[test]
fn translates_simple_call_expression_and_records_call_rule() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "call".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "call_hook".to_string(),
        c_source: "int call_hook(int value) { observe(value); return value; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result.rust_code.contains("observe(value);"));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"simple_call".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"simple-call".to_string()));
}

#[test]
fn translates_direct_call_expressions_and_records_callee_evidence() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "call-expression".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "call_expression".to_string(),
        c_source: "int call_expression(int value) { int first = helper(value); value = helper(first); return helper(value); }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("let mut first: i32 = helper(value);"));
    assert!(result.rust_code.contains("value = helper(first);"));
    assert!(result.rust_code.contains("return helper(value);"));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"call_expression".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"bounded-call-expression".to_string()));

    let plan = serde_json::to_value(&result.plan).unwrap();
    let calls = plan["call_expressions"].as_array().unwrap();
    assert_eq!(calls.len(), 3);
    assert_eq!(calls[0]["callee"], "helper");
    assert_eq!(calls[0]["arguments"], serde_json::json!(["value"]));
    assert_eq!(calls[1]["source_expression"], "helper(first)");
    assert_eq!(calls[2]["statement_context"], "return");
}

#[test]
fn blocks_unsupported_call_expressions_without_rust_draft() {
    for (slice_id, c_source) in [
        (
            "nested-call-expression",
            "int nested_call_expression(int value) { return helper(other(value)); }",
        ),
        (
            "function-pointer-call-expression",
            "int function_pointer_call_expression(int value) { return (*fp)(value); }",
        ),
        (
            "side-effect-call-argument",
            "int side_effect_call_argument(int value) { return helper(value++); }",
        ),
    ] {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: slice_id.to_string(),
            source_commit: "1234567".to_string(),
            function_name: slice_id.replace('-', "_"),
            c_source: c_source.to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(
            result.rust_code.is_empty(),
            "{slice_id}: {}",
            result.rust_code
        );
        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_syntax"),
            "{slice_id}: {:?}",
            result.errors
        );
    }
}

#[test]
fn translates_compound_assignment_statement_and_records_rule() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "compound-assignment".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "compound_assignment".to_string(),
        c_source:
            "int compound_assignment(int value) { value += 1; value-=1; value *= 2; return value; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn compound_assignment(mut value: i32) -> i32"));
    assert!(result.rust_code.contains("value += 1;"));
    assert!(result.rust_code.contains("value -= 1;"));
    assert!(result.rust_code.contains("value *= 2;"));
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"compound_assignment".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"compound-assignment".to_string()));
}

#[test]
fn translates_increment_and_decrement_statements_and_records_rule() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "inc-dec".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "inc_dec".to_string(),
        c_source: "int inc_dec(int value) { value++; --value; ++value; value--; return value; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn inc_dec(mut value: i32) -> i32"));
    assert_eq!(result.rust_code.matches("value += 1;").count(), 2);
    assert_eq!(result.rust_code.matches("value -= 1;").count(), 2);
    assert!(result.cfg.functions[0].blocks[0]
        .statement_kinds
        .contains(&"inc_dec".to_string()));
    assert!(result
        .plan
        .translation_rule_ids
        .contains(&"increment-decrement".to_string()));
}

#[test]
fn blocks_increment_expression_value_without_rust_draft() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "inc-expression".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "inc_expression".to_string(),
        c_source: "int inc_expression(int value) { return value++; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_syntax"));
}

#[test]
fn blocks_unknown_or_unsupported_statement_without_rust_draft() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "unsupported-stmt".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "unsupported_stmt".to_string(),
        c_source: "int unsupported_stmt(int value) { value ? value : 0; return value; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_syntax"));
}

#[test]
fn unsupported_goto_blocks_translation_without_false_success() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "goto-case".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "again".to_string(),
        c_source: "int again(int x) { again: x++; if (x < 10) goto again; return x; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_control_flow"));
    assert!(result.cfg.functions[0]
        .unsupported_control_flow
        .iter()
        .any(|node| node == "goto"));
}

#[test]
fn unsupported_switch_blocks_translation_until_cfg_relooper_exists() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "switch-case".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "choose".to_string(),
        c_source: "int choose(int x) { switch (x) { case 1: return 1; default: return 0; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_control_flow"));
    assert!(result.cfg.functions[0]
        .unsupported_control_flow
        .iter()
        .any(|node| node == "switch"));
}

#[test]
fn missing_clang_profile_records_type_uncertainty() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "ambiguous".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "uses_alias".to_string(),
        c_source: "alias_t uses_alias(alias_t value) { return value; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(false),
        ..SliceSpec::default()
    };

    let result = translate_slice(&spec);

    assert!(result.rust_code.is_empty());
    assert!(result
        .type_map
        .uncertainties
        .iter()
        .any(|item| item.reason.contains("clang-backed type extraction")));
    assert!(result
        .errors
        .iter()
        .any(|error| error.kind == "type_uncertainty"));
}

#[test]
fn writes_translation_artifacts_for_l3_manifest_binding() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "add-one".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "add_one".to_string(),
        c_source: "int add_one(int value) { return value + 1; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("add-one");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert_eq!(manifest.target_id, "demo");
    assert_eq!(manifest.slice_id, "add-one");
    for path in [
        "l3-add-one-auto-translation-plan.json",
        "l3-add-one-auto-translation-events.jsonl",
        "l3-add-one-type-map.json",
        "l3-add-one-cfg.json",
        "l3-add-one-pointer-graph.json",
        "l3-add-one-ai-candidate-manifest.json",
        "l3-add-one-blocked-repairs.json",
        "l3-add-one-rust-draft.rs",
    ] {
        assert!(out_dir.join(path).exists(), "{path}");
    }
    let plan = fs::read_to_string(out_dir.join("l3-add-one-auto-translation-plan.json")).unwrap();
    assert!(plan.contains("\"status\": \"generated\""));
}

#[cfg(not(feature = "clang-frontend"))]
#[test]
fn default_translation_artifacts_do_not_emit_clang_dry_run() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
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
            "include_paths": ["inc"],
            "defines": ["FDB_USING_FILE_POSIX_MODE"],
            "target_triple": "x86_64-unknown-linux-gnu",
            "abi": "linux-gnu",
            "compiler_command_source": "C:/src/FlashDB/CMakeLists.txt",
            "clang_available": false
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("no-clang-dry-run");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-dry-run.json")
        .exists());
    assert!(!out_dir
        .join("l3-real-fdb-calc-crc32-clang-lowering-report.json")
        .exists());
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-lowering-report.json")));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_frontend_feature_writes_dry_run_artifact_from_real_tu_metadata() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/FlashDB",
        "source_file": "src/fdb_utils.c",
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
    let out_dir = unique_out_dir("clang-dry-run");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let dry_run = json_file(out_dir.join("l3-real-fdb-calc-crc32-clang-dry-run.json"));

    assert!(manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
    assert_eq!(dry_run["schema_version"], 1);
    assert_eq!(dry_run["status"], "ready_without_libclang");
    assert_eq!(dry_run["frontend"], "clang");
    assert_eq!(dry_run["dry_run"]["source_file"], "src/fdb_utils.c");
    assert_eq!(
        dry_run["dry_run"]["arguments"],
        serde_json::json!([
            "-IC:/src/FlashDB/inc",
            "-IC:/src/FlashDB/tests",
            "-DFDB_USING_FILE_POSIX_MODE"
        ])
    );
    assert_eq!(
        dry_run["metadata"]["source_file_hashes"]["src/fdb_utils.c"],
        "source-file-sha"
    );
    assert!(dry_run["errors"].as_array().unwrap().is_empty());
}

#[cfg(all(feature = "clang-frontend", not(feature = "clang-lowering-report")))]
#[test]
fn clang_frontend_feature_does_not_emit_lowering_report_without_opt_in() {
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": "C:/src/demo",
        "source_file": "add_one.c",
        "source_file_hashes": {
            "add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "add_one.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 43,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("no-clang-lowering-report");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

    assert!(!out_dir
        .join("l3-add-one-clang-lowering-report.json")
        .exists());
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-add-one-clang-lowering-report.json")));
}

#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_feature_writes_report_artifact_without_changing_manifest_status() {
    let source_root = unique_out_dir("clang-lowering-source");
    fs::create_dir_all(&source_root).unwrap();
    fs::write(
        source_root.join("add_one.c"),
        "int add_one(int value) { return value + 1; }\n",
    )
    .unwrap();
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "demo",
        "slice_id": "add-one",
        "source_commit": "1234567",
        "function_name": "add_one",
        "c_source": "int add_one(int value) { return value + 1; }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root,
        "source_file": "add_one.c",
        "source_file_hashes": {
            "add_one.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "add_one.c",
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 43,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("clang-lowering-report");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let report = json_file(out_dir.join("l3-add-one-clang-lowering-report.json"));

    assert_eq!(manifest.status, "generated");
    assert!(manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-add-one-clang-lowering-report.json")));
    assert_eq!(report["schema_version"], 1);
    assert_eq!(report["artifact_kind"], "clang-lowering-report");
    assert_eq!(report["frontend"], "clang");
    assert_eq!(report["function_name"], "add_one");
    assert_eq!(report["claim_boundary"]["role"], "diagnostic_only");
    assert_eq!(report["claim_boundary"]["affects_manifest_status"], false);
    assert_eq!(report["claim_boundary"]["affects_semantic_pass"], false);
    assert_eq!(report["claim_boundary"]["authoritative_evidence"], false);
    assert!(["lowered", "unavailable", "blocked", "unsupported"]
        .contains(&report["status"].as_str().unwrap()));
    assert_eq!(report["lowering_report"]["function_name"], "add_one");
    assert_eq!(
        report["lowering_report"]["source_file"],
        report["source_file"]
    );
    assert!(report["typed_ir_candidate"].is_object());
    assert_eq!(report["typed_ir_candidate"]["semantic_pass"], false);
    assert!(report["typed_ir_candidate"]["readonly_globals"]
        .as_array()
        .is_some());
    if report["typed_ir_candidate"]["status"] == "generated" {
        assert_eq!(
            report["typed_ir_candidate"]["candidate_route"]["route"],
            "GenericTypedIr"
        );
        assert_eq!(
            report["typed_ir_candidate"]["candidate_route"]["candidate_generator"],
            "GenericTypedIrEmitter"
        );
    }
    assert_eq!(
        report["metadata"]["logical_source_file"],
        serde_json::json!("add_one.c")
    );
    assert!(report["diagnostics"].as_array().is_some());
    assert!(report["errors"].as_array().is_some());
    assert!(out_dir.join("l3-add-one-rust-draft.rs").exists());
}

#[cfg(feature = "clang-lowering-report")]
#[test]
fn clang_lowering_report_feature_can_drive_rust_draft_from_clang_lowered_ir_when_enabled() {
    if std::env::var("C2R_RUN_CLANG_AST_TESTS").ok().as_deref() != Some("1") {
        eprintln!("set C2R_RUN_CLANG_AST_TESTS=1 to run the real clang AST smoke test");
        return;
    }
    let clang_path = std::env::var("CLANG_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:/Program Files/LLVM/bin/clang.exe"));
    assert!(
        clang_path.exists(),
        "clang path does not exist: {}",
        clang_path.display()
    );
    let _clang_path_guard = EnvVarGuard::set_path("CLANG_PATH", &clang_path);
    let source_root = unique_out_dir("clang-lowered-rust-draft-source");
    fs::create_dir_all(source_root.join("src")).unwrap();
    fs::create_dir_all(source_root.join("inc")).unwrap();
    let table_values = repeated_c_u32_initializer(256, "0U");
    fs::write(
        source_root.join("src/fdb_utils.c"),
        format!(
            "#include <stdint.h>\n#include <stddef.h>\nstatic const uint32_t crc32_table[256] = {{ {table_values} }};\nuint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) {{\n    const uint8_t *p;\n    p = (const uint8_t *)buf;\n    crc = crc ^ ~0U;\n    while (size--) {{\n        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);\n    }}\n    return crc ^ ~0U;\n}}\n"
        ),
    )
    .unwrap();
    let source_root = source_root.to_string_lossy().replace('\\', "/");
    let spec: SliceSpec = serde_json::from_value(serde_json::json!({
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "source_commit": "93d1755",
        "function_name": "fdb_calc_crc32",
        "c_source": "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size) { return crc; }",
        "fixture_hash": "fixture-sha",
        "source_root": source_root,
        "source_file": "src/fdb_utils.c",
        "source_file_hashes": {
            "src/fdb_utils.c": "source-file-sha"
        },
        "function_source_span": {
            "file": "src/fdb_utils.c",
            "line_start": 4,
            "line_end": 12,
            "byte_start": 86,
            "byte_end": 357,
            "sha256": "function-span-sha"
        },
        "build_profile": {
            "include_paths": ["inc"],
            "defines": [],
            "target_triple": "x86_64-pc-windows-msvc",
            "abi": "msvc",
            "compiler_command_source": "clang",
            "clang_available": true
        }
    }))
    .unwrap();
    let out_dir = unique_out_dir("clang-lowered-rust-draft");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let plan = json_file(out_dir.join("l3-real-fdb-calc-crc32-auto-translation-plan.json"));
    let type_map = json_file(out_dir.join("l3-real-fdb-calc-crc32-type-map.json"));
    let cfg = json_file(out_dir.join("l3-real-fdb-calc-crc32-cfg.json"));
    let pointer_graph = json_file(out_dir.join("l3-real-fdb-calc-crc32-pointer-graph.json"));
    let report = json_file(out_dir.join("l3-real-fdb-calc-crc32-clang-lowering-report.json"));
    let rust = fs::read_to_string(out_dir.join("l3-real-fdb-calc-crc32-rust-draft.rs")).unwrap();

    assert_eq!(manifest.status, "generated");
    assert_eq!(report["typed_ir_candidate"]["status"], "generated");
    assert_eq!(
        report["typed_ir_candidate"]["candidate_route"]["route"],
        "GenericTypedIr"
    );
    assert_eq!(
        report["typed_ir_candidate"]["candidate_route"]["candidate_generator"],
        "GenericTypedIrEmitter"
    );
    assert_eq!(report["typed_ir_candidate"]["semantic_pass"], false);
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["name"],
        "crc32_table"
    );
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["array_len"],
        256
    );
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["init_kind"],
        "integer_array"
    );
    assert_eq!(
        report["typed_ir_candidate"]["readonly_globals"][0]["value_count"],
        256
    );
    assert!(rust.contains("const CRC32_TABLE: [u32; 256] = [0u32, 0u32"));
    assert!(
        rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], mut size: usize) -> u32")
    );
    assert!(rust.contains("CRC32_TABLE[((crc ^ (byte0 as u32)) &"));
    assert!(rust.contains("(255i32 as u32)") || rust.contains("255u32"));
    assert!(rust.contains("^ (crc >> 8"));
    assert!(!rust.contains("crc32_update_byte"));
    assert!(!rust.contains("return crc;"));
    assert!(plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("clang-lowered-typed-ir")));
    assert!(plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("byte-cursor-loop")));
    assert!(!plan["plan"]["translation_rule_ids"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("crc32-byte-cursor-loop")));
    assert!(type_map["type_map"]["mappings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|mapping| mapping["symbol"] == "buf" && mapping["rust_type"] == "&[u8]"));
    assert!(cfg["cfg"]["functions"][0]["blocks"][0]["statement_kinds"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("while")));
    assert_eq!(pointer_graph["status"], "recorded");
    assert!(pointer_graph["pointer_graph"]["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .any(|node| {
            node["id"] == "buf"
                && node["role"] == "borrowed_input"
                && node["rust_boundary"] == "&[u8]"
                && node["read_effects"]
                    .as_array()
                    .unwrap()
                    .contains(&serde_json::json!("*p++"))
                && node["boundary_decisions"]
                    .as_array()
                    .unwrap()
                    .contains(&serde_json::json!("byte_cursor_post_increment_read"))
        }));
}

#[cfg(feature = "clang-frontend")]
#[test]
fn clang_frontend_dry_run_artifact_records_metadata_errors_without_blocking_translation() {
    let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "add-one".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "add_one".to_string(),
        c_source: "int add_one(int value) { return value + 1; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };
    let out_dir = unique_out_dir("clang-dry-run-blocked");

    let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
    let dry_run = json_file(out_dir.join("l3-add-one-clang-dry-run.json"));

    assert_eq!(manifest.status, "generated");
    assert_eq!(dry_run["status"], "blocked");
    assert_eq!(dry_run["errors"][0]["kind"], "missing_source_root");
    assert_eq!(
        dry_run["errors"][0]["message"],
        "clang frontend dry-run requires source_root"
    );
    assert!(out_dir.join("l3-add-one-rust-draft.rs").exists());
}

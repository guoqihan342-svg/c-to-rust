use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

#[cfg(feature = "clang-frontend")]
use c2r_translator::clang_frontend::ClangParseSpec;
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
use c2r_translator::clang_frontend::{
    lower_function_from_clang_ast_dump, lower_function_from_clang_ast_dump_report,
    lower_function_skeleton, lower_function_skeleton_report, ClangBinaryOperator,
    ClangExprSkeleton, ClangFunctionSkeleton, ClangParamSkeleton, ClangStmtSkeleton, ClangTypeKind,
    ClangTypeSkeleton,
};
#[cfg(feature = "typed-ir")]
use c2r_translator::typed_ir::{
    emit_rust_from_ir, IrBinOp, IrExpr, IrFunction, IrIncDecOp, IrParam, IrStmt, IrType,
    IrTypeKind, IrUnOp,
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
    let int_ty = ir_i32();
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
        u8_ty.clone(),
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
        ir_lit(0xFF, "0xFF", int_ty.clone()),
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
        ir_lit(8, "8", int_ty.clone()),
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
#[test]
fn typed_ir_emits_flashdb_crc32_without_string_recognizer() {
    let rust = emit_rust_from_ir(&flashdb_crc32_typed_ir()).expect("typed IR crc32 emit");

    assert!(rust.contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], size: usize) -> u32"));
    assert!(rust.contains("let mut p: usize = 0;"));
    assert!(rust.contains("let mut remaining = size;"));
    assert!(rust.contains("while remaining != 0 {"));
    assert!(rust.contains("let byte = buf[p];"));
    assert!(rust.contains("p += 1;"));
    assert!(rust.contains("crc = crc32_update_byte(crc, byte);"));
    assert!(rust.contains("return crc ^ !0u32;"));
    assert!(!rust.contains("*p++"));
    assert!(!rust.contains("crc32_table"));
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
fn flashdb_crc32_byte_cursor_loop_generates_safe_slice_boundary_and_rules() {
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

    assert!(result.errors.is_empty(), "{:?}", result.errors);
    assert!(result
        .rust_code
        .contains("pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], size: usize) -> u32"));
    assert!(result.rust_code.contains("let mut p: usize = 0;"));
    assert!(result.rust_code.contains("let mut remaining = size;"));
    assert!(result.rust_code.contains("while remaining != 0 {"));
    assert!(result.rust_code.contains("let byte = buf[p];"));
    assert!(result.rust_code.contains("p += 1;"));
    assert!(result
        .rust_code
        .contains("crc = crc32_update_byte(crc, byte);"));
    assert!(!result.rust_code.contains("*p++"));
    assert!(!result.rust_code.contains("crc32_table"));
    let buf = result
        .pointer_graph
        .nodes
        .iter()
        .find(|node| node.id == "buf")
        .expect("buf pointer node");
    assert_eq!(buf.role, "borrowed_input");
    assert_eq!(buf.rust_boundary, "&[u8]");
    assert!(buf.read_effects.contains(&"*p++".to_string()));
    for rule in [
        "const-void-byte-slice",
        "byte-cursor-post-increment-read",
        "crc32-byte-cursor-loop",
        #[cfg(feature = "typed-ir")]
        "typed-ir-crc32-emitter",
    ] {
        assert!(
            result.plan.translation_rule_ids.contains(&rule.to_string()),
            "{rule}: {:?}",
            result.plan.translation_rule_ids
        );
    }
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
    assert!(!manifest
        .artifact_paths
        .iter()
        .any(|path| path.ends_with("l3-real-fdb-calc-crc32-clang-dry-run.json")));
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

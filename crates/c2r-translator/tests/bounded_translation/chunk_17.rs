#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn real_fdb_tsl_to_blob_ir_path(expr: &IrExpr) -> Option<Vec<String>> {
    match expr {
        IrExpr::Var { name, .. } => Some(vec![name.clone()]),
        IrExpr::Member { base, field, .. } => {
            let mut path = real_fdb_tsl_to_blob_ir_path(base)?;
            path.push(field.clone());
            Some(path)
        }
        IrExpr::LValueToRValue { expr, .. } => real_fdb_tsl_to_blob_ir_path(expr),
        _ => None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn real_fdb_tsl_to_blob_json_nodes_with_kind<'a>(
    value: &'a Value,
    kind: &str,
    nodes: &mut Vec<&'a Value>,
) {
    match value {
        Value::Object(object) => {
            if object.get("kind").and_then(Value::as_str) == Some(kind) {
                nodes.push(value);
            }
            for child in object.values() {
                real_fdb_tsl_to_blob_json_nodes_with_kind(child, kind, nodes);
            }
        }
        Value::Array(values) => {
            for child in values {
                real_fdb_tsl_to_blob_json_nodes_with_kind(child, kind, nodes);
            }
        }
        _ => {}
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn real_fdb_tsl_to_blob_fixture_and_abi() -> (Value, TargetAbiProfile) {
    let ast = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/real_fdb_tsl_to_blob_ast.json"
    ))
    .expect("real fdb_tsl_to_blob fixture JSON");
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
    (ast, target_abi)
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_real_fdb_tsl_to_blob_with_u32_widening_without_clang() {
    let (ast, target_abi) = real_fdb_tsl_to_blob_fixture_and_abi();
    let mut integral_casts = Vec::new();
    real_fdb_tsl_to_blob_json_nodes_with_kind(&ast, "ImplicitCastExpr", &mut integral_casts);
    let integral_casts = integral_casts
        .into_iter()
        .filter(|node| node.get("castKind").and_then(Value::as_str) == Some("IntegralCast"))
        .collect::<Vec<_>>();
    assert_eq!(integral_casts.len(), 1, "{integral_casts:?}");
    let clang_cast = integral_casts[0];
    assert_eq!(clang_cast["type"]["qualType"], "size_t");
    assert_eq!(clang_cast["type"]["desugaredQualType"], "unsigned long");
    assert_eq!(clang_cast["inner"][0]["type"]["qualType"], "uint32_t");
    assert_eq!(clang_cast["inner"][0]["inner"][0]["name"], "log_len");

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "fdb_tsl_to_blob",
        Some(&target_abi),
    )
    .expect("lower real FlashDB fdb_tsl_to_blob fixture without invoking clang");
    let [
        IrStmt::Assign {
            target: addr_target,
            value: addr_value,
            ..
        },
        IrStmt::Assign {
            target: meta_target,
            value: meta_value,
            ..
        },
        IrStmt::Assign {
            target: len_target,
            value: len_value,
            ..
        },
        IrStmt::Return {
            value: Some(return_value),
            ..
        },
    ] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected three field copies and identity return, got {:?}",
            lowered.function_ir.body
        );
    };

    assert_eq!(
        real_fdb_tsl_to_blob_ir_path(addr_target),
        Some(vec!["blob".into(), "saved".into(), "addr".into()])
    );
    assert_eq!(
        real_fdb_tsl_to_blob_ir_path(addr_value),
        Some(vec!["tsl".into(), "addr".into(), "log".into()])
    );
    assert_eq!(
        real_fdb_tsl_to_blob_ir_path(meta_target),
        Some(vec!["blob".into(), "saved".into(), "meta_addr".into()])
    );
    assert_eq!(
        real_fdb_tsl_to_blob_ir_path(meta_value),
        Some(vec!["tsl".into(), "addr".into(), "index".into()])
    );
    assert_eq!(
        real_fdb_tsl_to_blob_ir_path(len_target),
        Some(vec!["blob".into(), "saved".into(), "len".into()])
    );
    let IrExpr::Cast {
        target,
        expr,
        implicit: true,
        ..
    } = len_value
    else {
        panic!("expected typed IR widening cast, got {len_value:?}");
    };
    assert!(matches!(
        target.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 64
        }
    ));
    let IrExpr::LValueToRValue {
        target: source_type,
        expr: source_expr,
        ..
    } = expr.as_ref()
    else {
        panic!("expected uint32_t lvalue read below widening cast, got {expr:?}");
    };
    assert!(matches!(
        source_type.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    ));
    assert_eq!(
        real_fdb_tsl_to_blob_ir_path(source_expr),
        Some(vec!["tsl".into(), "log_len".into()])
    );
    assert_eq!(
        real_fdb_tsl_to_blob_ir_path(return_value),
        Some(vec!["blob".into()])
    );

    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "tsl".to_string(),
            mutable_param: "blob".to_string(),
        }],
        ..Default::default()
    };
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        policy,
    )
    .expect("emit Rust from real FlashDB fdb_tsl_to_blob fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(lowered.globals.is_empty());
    assert!(rust.contains("pub struct FdbTsl"), "{rust}");
    assert!(rust.contains("pub struct FdbTslAddr"), "{rust}");
    assert!(rust.contains("pub log_len: u32"), "{rust}");
    assert!(!rust.contains("pub log_len: usize"), "{rust}");
    assert!(rust.contains("pub struct FdbBlob"), "{rust}");
    assert!(rust.contains("pub struct FdbBlobSaved"), "{rust}");
    assert!(
        rust.contains("pub fn fdb_tsl_to_blob<'a>(tsl: &FdbTsl"),
        "{rust}"
    );
    assert!(rust.contains("blob: &'a mut FdbBlob"), "{rust}");
    assert!(rust.contains("blob.saved.addr = tsl.addr.log;"), "{rust}");
    assert!(
        rust.contains("blob.saved.meta_addr = tsl.addr.index;"),
        "{rust}"
    );
    assert!(
        rust.contains("blob.saved.len = (tsl.log_len as usize);"),
        "{rust}"
    );
    assert!(rust.contains("return blob;"), "{rust}");

    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-real-fdb-tsl-to-blob",
        rust,
        r#"
    for (log, index, log_len) in [
        (0u32, 0u32, 0u32),
        (4352u32, 4096u32, 128u32),
        (u32::MAX, u32::MAX, u32::MAX),
    ] {
        let tsl = FdbTsl {
            log_len,
            addr: FdbTslAddr { index, log },
        };
        let mut blob = FdbBlob {
            buf: core::ptr::null_mut(),
            size: 0,
            saved: FdbBlobSaved {
                meta_addr: 99,
                addr: 88,
                len: 77,
            },
        };
        let blob_ptr = &mut blob as *mut FdbBlob;
        let returned = fdb_tsl_to_blob(&tsl, &mut blob);
        assert_eq!(returned as *mut FdbBlob, blob_ptr);
        assert_eq!(returned.saved.addr, log);
        assert_eq!(returned.saved.meta_addr, index);
        assert_eq!(returned.saved.len, log_len as usize);
    }
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_real_fdb_tsl_to_blob_without_exact_noalias_refs() {
    let (ast, target_abi) = real_fdb_tsl_to_blob_fixture_and_abi();
    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "fdb_tsl_to_blob",
        Some(&target_abi),
    )
    .expect("lower real FlashDB fdb_tsl_to_blob fixture");

    for (label, policy) in [
        ("missing", EmitPolicy::default()),
        (
            "drifted refs",
            EmitPolicy {
                noalias_param_pairs: vec![NoAliasParamPair {
                    readonly_param: "tsl_drifted".to_string(),
                    mutable_param: "blob".to_string(),
                }],
                ..Default::default()
            },
        ),
    ] {
        let error = emit_rust_from_ir_with_globals_and_policy(
            &lowered.function_ir,
            &lowered.globals,
            policy,
        )
        .expect_err("missing or drifted noalias refs must fail closed");
        assert_eq!(error.route.route, CandidateRoute::Unsupported, "{label}");
        assert!(
            error.reason.contains("requires exactly one pointer param for alias proof"),
            "{label}: {error:?}"
        );
    }
}

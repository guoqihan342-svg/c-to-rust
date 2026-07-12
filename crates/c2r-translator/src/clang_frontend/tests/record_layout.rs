#[test]
fn record_layout_dump_parser_captures_named_size_and_alignment() {
    let dump = r#"
*** Dumping AST Record Layout
         0 | struct point
         0 |   int x
         4 |   int y
           | [sizeof=8, align=4]

*** Dumping AST Record Layout
         0 | struct other
         0 |   unsigned char tag
           | [sizeof=1, align=1]
"#;

    let (layouts, ambiguous) = parse_record_layout_dump(dump).expect("parse layouts");

    assert!(ambiguous.is_empty());
    assert_eq!(layouts["struct point"].size_bytes, 8);
    assert_eq!(layouts["struct point"].align_bytes, 4);
    assert_eq!(layouts["struct other"].size_bytes, 1);
}

#[test]
fn record_layout_dump_parser_removes_duplicate_named_records() {
    let dump = r#"
*** Dumping AST Record Layout
         0 | struct point
           | [sizeof=8, align=4]
*** Dumping AST Record Layout
         0 | struct point
           | [sizeof=16, align=8]
"#;

    let (layouts, ambiguous) = parse_record_layout_dump(dump).expect("parse layouts");

    assert!(!layouts.contains_key("struct point"));
    assert_eq!(ambiguous, vec!["struct point"]);
}

#[test]
fn record_layout_arguments_replace_exact_ast_dump_pair() {
    let ast = vec![
        "-Xclang".to_string(),
        "-ast-dump=json".to_string(),
        "-fsyntax-only".to_string(),
        "unit.c".to_string(),
    ];

    let layout = record_layout_dump_arguments(&ast).expect("layout arguments");

    assert_eq!(&layout[..2], ["-Xclang", "-fdump-record-layouts-complete"]);
    assert!(!layout.iter().any(|item| item == "-ast-dump=json"));
    assert!(layout.iter().any(|item| item == "unit.c"));

    let error = record_layout_dump_arguments(&["-fsyntax-only".to_string()])
        .expect_err("missing AST dump pair must fail closed");
    assert_eq!(error.kind, "invalid_clang_record_layout_arguments");
}

#[test]
fn record_layout_binding_lowers_record_sizeof_to_bound_literal() {
    let size_t = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let record = ClangTypeSkeleton {
        spelled: "struct point".to_string(),
        canonical: "struct point".to_string(),
        kind: ClangTypeKind::Record {
            name: "point".to_string(),
        },
    };
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        int_width: 32,
        char_width: 8,
        long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };
    let mut function = ClangFunctionSkeleton {
        name: "record_bytes".to_string(),
        return_type: size_t.clone(),
        params: Vec::new(),
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::SizeOfType {
                arg_type: record,
                ty: size_t,
                record_layout: None,
                target_abi: Some(target_abi.clone()),
            }),
        }],
    };
    let layout = ClangRecordLayout {
        record_type: "struct point".to_string(),
        size_bytes: 8,
        align_bytes: 4,
    };
    let layouts = BTreeMap::from([("struct point".to_string(), layout.clone())]);
    let dump = RecordLayoutDump {
        arguments: vec!["-fsyntax-only".to_string(), "unit.c".to_string()],
        dump_sha256: "a".repeat(64),
        diagnostics_sha256: "b".repeat(64),
        compile_arguments_sha256: "c".repeat(64),
        compile_database_sha256: "d".repeat(64),
        target_abi: target_abi.clone(),
        layouts,
        ambiguous_records: Vec::new(),
    };

    let used = bind_record_layouts_to_function_skeleton(&mut function, &dump);
    let lowered = lower_function_skeleton(&function).expect("lower record sizeof");

    assert_eq!(used.len(), 1);
    assert_eq!(used[0].record_type, layout.record_type);
    assert_eq!(used[0].size_bytes, layout.size_bytes);
    assert_eq!(used[0].target_abi, target_abi);
    let IrStmt::Return {
        value: Some(IrExpr::LitInt { value, .. }),
        ..
    } = &lowered.body[0]
    else {
        panic!("expected record sizeof literal, got {:?}", lowered.body[0]);
    };
    assert_eq!(*value, 8);

    let mut mismatched = function.clone();
    let ClangStmtSkeleton::Return {
        value:
            Some(ClangExprSkeleton::SizeOfType {
                record_layout: Some(binding),
                ..
            }),
        ..
    } = &mut mismatched.body[0]
    else {
        panic!("expected bound record sizeof skeleton");
    };
    binding.record_type = "struct other".to_string();
    let error = lower_function_skeleton(&mismatched)
        .expect_err("layout from another record must fail closed");
    assert_eq!(error.kind, "invalid_record_layout_binding");

    let mut target_mismatch = function;
    let ClangStmtSkeleton::Return {
        value:
            Some(ClangExprSkeleton::SizeOfType {
                record_layout: Some(binding),
                ..
            }),
        ..
    } = &mut target_mismatch.body[0]
    else {
        panic!("expected bound record sizeof skeleton");
    };
    binding.target_abi.triple_or_abi = "aarch64-unknown-linux-gnu".to_string();
    let error = lower_function_skeleton(&target_mismatch)
        .expect_err("layout from another target must fail closed");
    assert_eq!(error.kind, "invalid_record_layout_binding");
}

#[test]
fn record_memset_bitcast_accepts_renamed_mutable_record_pointer_only_for_memset() {
    let argument = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "BitCast",
        "type": {"qualType": "void *"},
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": {"qualType": "struct renamed_packet *"},
            "inner": [{
                "kind": "DeclRefExpr",
                "type": {"qualType": "struct renamed_packet *"},
                "referencedDecl": {
                    "kind": "ParmVarDecl",
                    "name": "output"
                }
            }]
        }]
    });

    let accepted = memory_destination_arg_skeleton_from_ast(&argument, "memset")
        .expect("parse renamed record pointer memset destination");
    assert!(matches!(
        accepted,
        ClangExprSkeleton::DeclRef { name, ty }
            if name == "output"
                && clang_mutable_record_pointer_record_name(&ty) == Some("renamed_packet")
    ));

    let rejected = memory_destination_arg_skeleton_from_ast(&argument, "memcpy")
        .expect("represent unsupported memcpy record destination");
    assert!(matches!(
        rejected,
        ClangExprSkeleton::Unsupported { reason, .. }
            if reason.contains("supported mutable byte or record pointer")
    ));
}

#[test]
fn record_memset_lowering_requires_same_bound_record_sizeof() {
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        int_width: 32,
        char_width: 8,
        long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };
    let record = ClangTypeSkeleton {
        spelled: "struct renamed_packet".to_string(),
        canonical: "struct renamed_packet".to_string(),
        kind: ClangTypeKind::Record {
            name: "renamed_packet".to_string(),
        },
    };
    let destination_type = ClangTypeSkeleton {
        spelled: "struct renamed_packet *".to_string(),
        canonical: "struct renamed_packet *".to_string(),
        kind: ClangTypeKind::Pointer {
            pointee: Box::new(record.clone()),
            width: Some(64),
        },
    };
    let size_type = ClangTypeSkeleton {
        spelled: "size_t".to_string(),
        canonical: "size_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 64,
        },
    };
    let layout = ClangRecordLayoutBinding {
        record_type: "struct renamed_packet".to_string(),
        size_bytes: 16,
        align_bytes: 8,
        dump_sha256: "a".repeat(64),
        diagnostics_sha256: "b".repeat(64),
        compile_arguments_sha256: "c".repeat(64),
        compile_database_sha256: "d".repeat(64),
        target_abi: target_abi.clone(),
    };
    let statement = ClangStmtSkeleton::Expr {
        expr: ClangExprSkeleton::Call {
            callee: "memset".to_string(),
            args: vec![
                ClangExprSkeleton::DeclRef {
                    name: "output".to_string(),
                    ty: destination_type,
                },
                ClangExprSkeleton::IntegerLiteral {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: ClangTypeSkeleton {
                        spelled: "int".to_string(),
                        canonical: "int".to_string(),
                        kind: ClangTypeKind::Integer {
                            signed: true,
                            width: 32,
                        },
                    },
                },
                ClangExprSkeleton::SizeOfType {
                    arg_type: record,
                    ty: size_type,
                    record_layout: Some(layout),
                    target_abi: Some(target_abi),
                },
            ],
            ty: ClangTypeSkeleton {
                spelled: "void *".to_string(),
                canonical: "void *".to_string(),
                kind: ClangTypeKind::Pointer {
                    pointee: Box::new(ClangTypeSkeleton {
                        spelled: "void".to_string(),
                        canonical: "void".to_string(),
                        kind: ClangTypeKind::Void,
                    }),
                    width: Some(64),
                },
            },
        },
    };

    let lowered = lower_stmt(&statement).expect("lower bound record memset");
    assert!(matches!(
        lowered,
        IrStmt::RecordMemset {
            destination: IrExpr::Var { name, .. },
            byte: 0,
            write_len_bytes: 16,
            layout: crate::typed_ir::IrRecordLayoutBinding { record_type, .. },
            ..
        } if name == "output" && record_type == "struct renamed_packet"
    ));

    let mut mismatched = statement.clone();
    let ClangStmtSkeleton::Expr {
        expr: ClangExprSkeleton::Call { args, .. },
    } = &mut mismatched
    else {
        panic!("expected record memset call skeleton");
    };
    let ClangExprSkeleton::SizeOfType { arg_type, .. } = &mut args[2] else {
        panic!("expected bound sizeof argument");
    };
    *arg_type = ClangTypeSkeleton {
        spelled: "struct unrelated".to_string(),
        canonical: "struct unrelated".to_string(),
        kind: ClangTypeKind::Record {
            name: "unrelated".to_string(),
        },
    };
    let error = lower_stmt(&mismatched).expect_err("different sizeof record must fail closed");
    assert_eq!(error.kind, "unsupported_record_memset");

    let mut unbound = statement;
    let ClangStmtSkeleton::Expr {
        expr: ClangExprSkeleton::Call { args, .. },
    } = &mut unbound
    else {
        panic!("expected record memset call skeleton");
    };
    let ClangExprSkeleton::SizeOfType { record_layout, .. } = &mut args[2] else {
        panic!("expected bound sizeof argument");
    };
    *record_layout = None;
    let error = lower_stmt(&unbound).expect_err("unbound sizeof must fail closed");
    assert_eq!(error.kind, "unsupported_record_memset");
}

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

use super::source_span_selector::select_expanded_function_name_by_source_span;
use sha2::{Digest as SourceSpanDigest, Sha256 as SourceSpanSha256};

fn source_span(file: &str) -> SourceSpanRef {
    SourceSpanRef {
        file: file.to_string(),
        line_start: 7,
        line_end: 9,
        byte_start: 120,
        byte_end: 181,
        sha256: "fixture-hash".to_string(),
    }
}

fn body_function(name: &str, file: Option<&str>) -> Value {
    let mut expansion_location = serde_json::json!({
        "offset": 124,
        "line": 7,
        "col": 5,
        "tokLen": 14
    });
    if let Some(file) = file {
        expansion_location["file"] = Value::String(file.to_string());
    }
    serde_json::json!({
        "kind": "FunctionDecl",
        "name": name,
        "loc": {
            "spellingLoc": {
                "offset": 1,
                "file": "<scratch space>",
                "line": 3,
                "col": 1,
                "tokLen": 12
            },
            "expansionLoc": expansion_location
        },
        "range": {
            "begin": { "offset": 120, "col": 1, "tokLen": 3 },
            "end": { "offset": 180, "line": 9, "col": 1, "tokLen": 1 }
        },
        "inner": [
            { "kind": "ParmVarDecl", "name": "value" },
            { "kind": "CompoundStmt", "inner": [] }
        ]
    })
}

#[test]
fn source_span_selector_returns_generic_macro_expanded_function_name() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "FunctionDecl",
                "name": "logical_entry",
                "loc": { "offset": 40, "file": "/workspace/src/module.c", "line": 3 },
                "range": {
                    "begin": { "offset": 36 },
                    "end": { "offset": 58, "tokLen": 1 }
                }
            },
            body_function("exported_entry", Some("/workspace/src/module.c"))
        ]
    });

    let selected = select_expanded_function_name_by_source_span(
        &ast,
        Path::new("/workspace/./src/module.c"),
        &source_span("src\\module.c"),
    )
    .expect("select unique body by macro expansion source evidence");

    assert_eq!(selected, "exported_entry");
    assert!(find_function_decl(&ast, "logical_entry").is_some());
}

#[test]
fn source_span_selector_rejects_file_evidence_omitted_across_functions() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "FunctionDecl",
                "name": "earlier_definition",
                "loc": { "offset": 4, "file": "/workspace/src/unit.c", "line": 1 },
                "range": {
                    "begin": { "offset": 0 },
                    "end": { "offset": 30, "tokLen": 1 }
                },
                "inner": [{ "kind": "CompoundStmt" }]
            },
            body_function("expanded_unit_entry", None)
        ]
    });

    let error = select_expanded_function_name_by_source_span(
        &ast,
        Path::new("/workspace/src/unit.c"),
        &source_span("src/unit.c"),
    )
    .expect_err("file evidence must not leak across FunctionDecl nodes");

    assert_eq!(error.kind, "function_decl_source_span_mismatch");
}

#[test]
fn source_span_selector_rejects_file_byte_and_line_mismatches() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [body_function("expanded_handler", Some("/workspace/src/handler.c"))]
    });

    for (source_file, span) in [
        (
            Path::new("/workspace/src/other.c"),
            source_span("src/handler.c"),
        ),
        (
            Path::new("/workspace/src/handler.c"),
            SourceSpanRef {
                byte_end: 182,
                ..source_span("src/handler.c")
            },
        ),
        (
            Path::new("/workspace/src/handler.c"),
            SourceSpanRef {
                line_end: 10,
                ..source_span("src/handler.c")
            },
        ),
    ] {
        assert!(
            select_expanded_function_name_by_source_span(&ast, source_file, &span).is_err(),
            "mismatched source evidence must fail closed: {source_file:?} {span:?}"
        );
    }
}

#[test]
fn source_span_selector_rejects_ambiguous_body_definitions() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            body_function("expanded_alpha", Some("/workspace/src/shared.c")),
            body_function("expanded_beta", Some("/workspace/src/shared.c"))
        ]
    });

    let error = select_expanded_function_name_by_source_span(
        &ast,
        Path::new("/workspace/src/shared.c"),
        &source_span("src/shared.c"),
    )
    .expect_err("duplicate source-span matches must fail closed");

    assert_eq!(error.kind, "ambiguous_function_decl_source_span");
}

#[test]
fn source_span_selector_rejects_matched_definition_without_expanded_name() {
    let mut definition = body_function("expanded_name", Some("/workspace/src/unnamed.c"));
    definition
        .as_object_mut()
        .expect("function fixture object")
        .remove("name");
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [definition]
    });

    let error = select_expanded_function_name_by_source_span(
        &ast,
        Path::new("/workspace/src/unnamed.c"),
        &source_span("src/unnamed.c"),
    )
    .expect_err("matched definition without expanded name must fail closed");

    assert_eq!(error.kind, "invalid_function_decl_source_span_match");
}

#[test]
fn source_span_selector_maps_normalized_lf_offsets_to_crlf_source_offsets() {
    let mut normalized = vec![b'x'; 200];
    for offset in [10usize, 20, 30] {
        normalized[offset] = b'\n';
    }
    let raw = normalized
        .iter()
        .flat_map(|byte| {
            if *byte == b'\n' {
                vec![b'\r', b'\n']
            } else {
                vec![*byte]
            }
        })
        .collect::<Vec<_>>();
    let unique = format!(
        "c2r-source-span-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock")
            .as_nanos()
    );
    let temp_dir = std::env::temp_dir().join(unique);
    std::fs::create_dir_all(&temp_dir).expect("create source-span temp dir");
    let source_file = temp_dir.join("unit.c");
    std::fs::write(&source_file, raw).expect("write CRLF source fixture");
    let span = SourceSpanRef {
        file: source_file.to_string_lossy().into_owned(),
        line_start: 7,
        line_end: 9,
        byte_start: 120,
        byte_end: 181,
        sha256: format!("{:x}", SourceSpanSha256::digest(&normalized[120..181])),
    };
    let mut definition = body_function("expanded_crlf_entry", Some(&span.file));
    definition["loc"]["expansionLoc"]["offset"] = serde_json::json!(127);
    definition["range"]["begin"]["offset"] = serde_json::json!(123);
    definition["range"]["end"]["offset"] = serde_json::json!(183);
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [definition]
    });

    let selected = select_expanded_function_name_by_source_span(&ast, &source_file, &span)
        .expect("normalized source evidence should map to raw CRLF offsets");

    assert_eq!(selected, "expanded_crlf_entry");
    std::fs::remove_dir_all(temp_dir).expect("remove source-span temp dir");
}

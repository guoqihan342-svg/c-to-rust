use std::collections::BTreeSet;
use std::io::Cursor;

use c2r_translator::rust_source_witness::{
    build_rust_source_witness, build_rust_source_witness_from_reader,
    rust_source_witness_json_bytes, MAX_RUST_SOURCE_BYTES, QUOTE_VERSION, SYN_PARSER_VERSION,
};

#[test]
fn extracts_nested_pre_cfg_project_facts_without_closure_authority() {
    let source = br#"
#![allow(dead_code)]
#[cfg(feature = "fast")]
pub mod api {
    #[repr(C)]
    pub struct Pair {
        #[cfg(target_pointer_width = "64")]
        pub left: i64,
        pub right: i32,
    }

    pub static mut TOTAL: i32 = 0;
    pub extern "C" fn add(value: i32) -> i32 { value + 1 }
}
"#;
    let witness = build_rust_source_witness(source);

    assert_eq!(witness.status, "ready");
    assert_eq!(witness.parser.implementation, "syn");
    assert_eq!(witness.parser.version, SYN_PARSER_VERSION);
    assert_eq!(witness.parser.quote_version, QUOTE_VERSION);
    assert_eq!(witness.modules.len(), 2);
    assert!(witness
        .items
        .iter()
        .any(|item| { item.item_path == "crate::api::add" && item.kind == "function" }));
    let signature = witness
        .signatures
        .iter()
        .find(|fact| fact.kind == "function")
        .expect("function signature");
    assert!(signature.syntax.contains("extern \"C\" fn add"));
    assert_eq!(signature.abi.as_deref(), Some("extern \"C\""));
    assert!(witness
        .types
        .iter()
        .any(|fact| { fact.kind == "struct" && fact.field_count == 2 }));
    assert!(witness
        .globals
        .iter()
        .any(|fact| { fact.kind == "static" && fact.mutable && fact.has_initializer }));
    assert!(witness
        .initialization
        .iter()
        .any(|fact| { fact.kind == "static-initializer" && fact.order == "unresolved-pre-cfg" }));
    assert_eq!(
        witness
            .attributes
            .iter()
            .filter(|fact| fact.kind == "cfg")
            .count(),
        2,
    );
    assert!(witness.claim_boundary.candidate_only);
    assert!(!witness.claim_boundary.post_cfg);
    assert!(!witness.claim_boundary.section_closure);
    assert!(!witness.claim_boundary.semantic_gate);
    assert_eq!(witness.claim_boundary.translation_coverage_numerator, 0);
}

#[test]
fn macro_cfg_attr_custom_attribute_and_external_module_block_explicitly() {
    let source = br#"
#[cfg_attr(feature = "derive", derive(Clone))]
mod external;

#[vendor::rewrites_signature]
pub fn render() { println!("value"); }
"#;
    let witness = build_rust_source_witness(source);
    let codes = blocker_codes(&witness);

    assert_eq!(witness.status, "blocked");
    assert!(codes.contains("rust_source_cfg_attr_unresolved"));
    assert!(codes.contains("rust_source_external_module_unresolved"));
    assert!(codes.contains("rust_source_unsupported_attribute"));
    assert!(codes.contains("rust_source_macro_expansion_required"));
    assert!(witness
        .attributes
        .iter()
        .any(|fact| { fact.kind == "cfg_attr" && fact.requires_expansion }));
    assert_eq!(witness.macro_invocations.len(), 1);
    assert_eq!(witness.macro_invocations[0].path, "println");
}

#[test]
fn invalid_utf8_parse_failure_and_empty_source_fail_closed() {
    let invalid_utf8 = build_rust_source_witness(&[0xff, 0xfe]);
    assert_eq!(invalid_utf8.status, "blocked");
    assert_eq!(invalid_utf8.source.encoding, "invalid-utf-8");
    assert!(blocker_codes(&invalid_utf8).contains("rust_source_invalid_utf8"));

    let invalid_syntax = build_rust_source_witness(b"pub fn {");
    assert!(blocker_codes(&invalid_syntax).contains("rust_source_parse_failed"));
    assert!(invalid_syntax.items.is_empty());

    let empty = build_rust_source_witness(b"");
    assert!(blocker_codes(&empty).contains("rust_source_no_items"));
    assert!(!empty.claim_boundary.section_closure);
}

#[test]
fn streamed_source_limit_is_hash_bound_and_fail_closed() {
    let source = vec![b' '; MAX_RUST_SOURCE_BYTES + 1];
    let witness =
        build_rust_source_witness_from_reader(Cursor::new(&source)).expect("bounded reader result");

    assert_eq!(witness.source.size_bytes, source.len() as u64);
    assert_eq!(witness.source.encoding, "not-inspected");
    assert!(blocker_codes(&witness).contains("rust_source_size_limit_exceeded"));
    assert!(witness.items.is_empty());
}

#[test]
fn serialized_witness_is_deterministic_bounded_jsonl() {
    let source = b"pub fn value(input: u32) -> u32 { input }\n";
    let first = build_rust_source_witness(source);
    let second = build_rust_source_witness(source);
    let first_json = rust_source_witness_json_bytes(&first).expect("first JSON");
    let second_json = rust_source_witness_json_bytes(&second).expect("second JSON");

    assert_eq!(first, second);
    assert_eq!(first_json, second_json);
    assert!(first_json.ends_with(b"\n"));
    let payload: serde_json::Value = serde_json::from_slice(&first_json).expect("valid JSON");
    assert_eq!(payload["source"]["sha256"], first.source.sha256);
    assert_eq!(payload["claim_boundary"]["section_closure"], false);
}

fn blocker_codes(
    witness: &c2r_translator::rust_source_witness::RustSourceWitness,
) -> BTreeSet<&str> {
    witness
        .blockers
        .iter()
        .map(|blocker| blocker.code)
        .collect()
}

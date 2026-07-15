mod associated;
mod collector;
mod fact_recording;
mod item_support;
mod items;
mod model;
mod scan_recording;
mod syntax_scan;

use std::io::{self, Read};

use sha2::{Digest, Sha256};

pub use model::*;

use collector::Collector;

pub const RUST_SOURCE_WITNESS_SCHEMA_VERSION: u32 = 1;
pub const RUST_SOURCE_WITNESS_PROTOCOL_VERSION: u32 = 1;
pub const SYN_PARSER_VERSION: &str = "2.0.118";
pub const QUOTE_VERSION: &str = "1.0.46";
pub const MAX_RUST_SOURCE_BYTES: usize = 4 * 1024 * 1024;
pub const MAX_RUST_SOURCE_STREAM_BYTES: u64 = 64 * 1024 * 1024;
pub const MAX_RUST_WITNESS_OUTPUT_BYTES: usize = 16 * 1024 * 1024;

pub fn build_rust_source_witness(source: &[u8]) -> RustSourceWitness {
    let identity = SourceIdentity {
        sha256: sha256_bytes(source),
        size_bytes: source.len() as u64,
        encoding: if source.len() <= MAX_RUST_SOURCE_BYTES {
            "utf-8"
        } else {
            "not-inspected"
        },
    };
    if source.len() > MAX_RUST_SOURCE_BYTES {
        return blocked_witness(identity, "rust_source_size_limit_exceeded", None);
    }
    build_retained_source_witness(identity, source)
}

pub fn build_rust_source_witness_from_reader<R: Read>(
    mut reader: R,
) -> io::Result<RustSourceWitness> {
    let mut digest = Sha256::new();
    let mut retained = Vec::new();
    let mut total = 0_u64;
    let mut chunk = [0_u8; 8192];
    loop {
        let count = reader.read(&mut chunk)?;
        if count == 0 {
            break;
        }
        total = total.checked_add(count as u64).ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "rust source byte count overflow",
            )
        })?;
        if total > MAX_RUST_SOURCE_STREAM_BYTES {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "rust source stream limit exceeded",
            ));
        }
        digest.update(&chunk[..count]);
        if retained.len() < MAX_RUST_SOURCE_BYTES {
            let remaining = MAX_RUST_SOURCE_BYTES - retained.len();
            retained.extend_from_slice(&chunk[..count.min(remaining)]);
        }
    }
    let source = SourceIdentity {
        sha256: format!("{:x}", digest.finalize()),
        size_bytes: total,
        encoding: if total <= MAX_RUST_SOURCE_BYTES as u64 {
            "utf-8"
        } else {
            "not-inspected"
        },
    };
    if total > MAX_RUST_SOURCE_BYTES as u64 {
        return Ok(blocked_witness(
            source,
            "rust_source_size_limit_exceeded",
            None,
        ));
    }
    Ok(build_retained_source_witness(source, &retained))
}

pub fn rust_source_witness_json_bytes(
    witness: &RustSourceWitness,
) -> Result<Vec<u8>, serde_json::Error> {
    let mut bytes = serde_json::to_vec(witness)?;
    bytes.push(b'\n');
    if bytes.len() <= MAX_RUST_WITNESS_OUTPUT_BYTES {
        return Ok(bytes);
    }
    let replacement = blocked_witness(
        witness.source.clone(),
        "rust_source_output_limit_exceeded",
        None,
    );
    let mut bounded = serde_json::to_vec(&replacement)?;
    bounded.push(b'\n');
    Ok(bounded)
}

fn build_retained_source_witness(mut source: SourceIdentity, bytes: &[u8]) -> RustSourceWitness {
    let text = match std::str::from_utf8(bytes) {
        Ok(value) => value,
        Err(error) => {
            source.encoding = "invalid-utf-8";
            return blocked_witness(
                source,
                "rust_source_invalid_utf8",
                Some(sha256_text(&error.to_string())),
            );
        }
    };
    let file = match syn::parse_file(text) {
        Ok(value) => value,
        Err(error) => {
            return blocked_witness(
                source,
                "rust_source_parse_failed",
                Some(sha256_text(&error.to_string())),
            );
        }
    };
    let mut collector = Collector::new();
    collector.collect_file(&file);
    let parts = collector.into_parts();
    RustSourceWitness {
        schema_version: RUST_SOURCE_WITNESS_SCHEMA_VERSION,
        artifact_kind: "rust-source-pre-cfg-witness",
        status: if parts.blockers.is_empty() {
            "ready"
        } else {
            "blocked"
        },
        parser: parser_identity(),
        source,
        modules: parts.modules,
        items: parts.items,
        signatures: parts.signatures,
        types: parts.types,
        globals: parts.globals,
        initialization: parts.initialization,
        attributes: parts.attributes,
        macro_invocations: parts.macro_invocations,
        blockers: parts.blockers,
        claim_boundary: claim_boundary(),
    }
}

fn blocked_witness(
    source: SourceIdentity,
    code: &'static str,
    detail_sha256: Option<String>,
) -> RustSourceWitness {
    RustSourceWitness {
        schema_version: RUST_SOURCE_WITNESS_SCHEMA_VERSION,
        artifact_kind: "rust-source-pre-cfg-witness",
        status: "blocked",
        parser: parser_identity(),
        source,
        modules: Vec::new(),
        items: Vec::new(),
        signatures: Vec::new(),
        types: Vec::new(),
        globals: Vec::new(),
        initialization: Vec::new(),
        attributes: Vec::new(),
        macro_invocations: Vec::new(),
        blockers: vec![Blocker {
            code,
            item_id: None,
            detail_sha256,
        }],
        claim_boundary: claim_boundary(),
    }
}

fn parser_identity() -> ParserIdentity {
    ParserIdentity {
        implementation: "syn",
        version: SYN_PARSER_VERSION,
        quote_version: QUOTE_VERSION,
        protocol_version: RUST_SOURCE_WITNESS_PROTOCOL_VERSION,
        crate_version: env!("CARGO_PKG_VERSION"),
    }
}

fn claim_boundary() -> ClaimBoundary {
    ClaimBoundary {
        phase: "pre-cfg",
        candidate_only: true,
        post_cfg: false,
        section_closure: false,
        semantic_gate: false,
        translation_coverage_numerator: 0,
    }
}

pub(super) fn sha256_text(value: &str) -> String {
    sha256_bytes(value.as_bytes())
}

fn sha256_bytes(value: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(value);
    format!("{:x}", digest.finalize())
}

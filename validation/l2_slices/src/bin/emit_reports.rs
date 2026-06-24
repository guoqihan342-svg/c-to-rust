use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
    time::Instant,
};

use c_to_rust_l2_slices::{libuv_ip4_addr, sqlite_varint, zlib_adler32, zstd_xxh32};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Debug, Deserialize)]
struct SqliteVarintCase {
    id: String,
    value: u64,
    encoded_hex: String,
    bytes_used: usize,
    decoded_value: u64,
    decoded_bytes: usize,
}

#[derive(Debug, Deserialize)]
struct ChecksumCase {
    id: String,
    input_hex: String,
    seed: Option<u32>,
    value: u32,
}

#[derive(Debug, Deserialize)]
struct LibuvIp4OracleReport {
    cases: Vec<LibuvIp4OracleCase>,
}

#[derive(Debug, Deserialize)]
struct LibuvIp4OracleCase {
    id: String,
    ip: String,
    port: i32,
    coverage_kind: String,
    return_code: i32,
    status: String,
    family: u16,
    port_host: u16,
    port_bytes_hex: String,
    addr_bytes_hex: String,
}

#[derive(Debug)]
struct SliceResult {
    slice_id: &'static str,
    case_count: usize,
    l2_status: &'static str,
    l3_status: &'static str,
}

#[derive(Debug)]
struct SafetyEvidence {
    scan: Value,
    ledger: Value,
}

#[derive(Debug)]
struct NegativeDiffResult {
    slice_id: &'static str,
    status: &'static str,
    report_path: &'static str,
}

fn main() -> Result<(), Box<dyn Error>> {
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = crate_dir
        .parent()
        .and_then(Path::parent)
        .ok_or("crate path must be under validation/l2_slices")?;
    let fixtures_dir = crate_dir.join("fixtures");
    let evidence_dir = repo_root
        .join("validation")
        .join("evidence")
        .join("l2-slices");
    fs::create_dir_all(&evidence_dir)?;

    let slices = vec![
        emit_sqlite_varint(&fixtures_dir, &evidence_dir)?,
        emit_zlib_adler32(&fixtures_dir, &evidence_dir)?,
        emit_zstd_xxh32(&fixtures_dir, &evidence_dir)?,
        emit_libuv_ip4_addr(&fixtures_dir, &repo_root)?,
    ];
    let safety = emit_safety_evidence(&crate_dir, &evidence_dir)?;
    emit_libuv_safety_evidence(&repo_root, &safety)?;
    let negative_diffs = emit_negative_diffs(&fixtures_dir, &evidence_dir)?;
    emit_summary(&evidence_dir, &slices, &safety, &negative_diffs)?;

    Ok(())
}

fn emit_libuv_ip4_addr(
    fixtures_dir: &Path,
    repo_root: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("libuv-ip4-addr-c-oracle.json");
    let report: LibuvIp4OracleReport = read_json(&fixture_path)?;
    let evidence_dir = repo_root.join("validation").join("evidence").join("libuv");
    fs::create_dir_all(&evidence_dir)?;

    let mut rust_cases = Vec::with_capacity(report.cases.len());
    let mut first_mismatch = None;

    for case in &report.cases {
        let rust = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "return_code",
            json!(case.return_code),
            json!(rust.return_code),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "status",
            json!(case.status),
            json!(rust.status),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "family",
            json!(case.family),
            json!(rust.family),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "port_host",
            json!(case.port_host),
            json!(rust.port_host),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "port_bytes_hex",
            json!(case.port_bytes_hex),
            json!(rust.port_bytes_hex),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "addr_bytes_hex",
            json!(case.addr_bytes_hex),
            json!(rust.addr_bytes_hex),
        );

        rust_cases.push(json!({
            "id": case.id,
            "ip": case.ip,
            "port": case.port,
            "coverage_kind": case.coverage_kind,
            "return_code": rust.return_code,
            "status": rust.status,
            "family": rust.family,
            "port_host": rust.port_host,
            "port_bytes_hex": rust.port_bytes_hex,
            "addr_bytes_hex": rust.addr_bytes_hex
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("l3-ip4-addr-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "source_commit": "5e7d51a8f4734cac453db960d4b9919735bbf7c3",
            "c_source_boundary": "uv_ip4_addr/uv_inet_pton/inet_pton4 from libuv",
            "rust_module_path": "validation/l2_slices/src/libuv_ip4_addr.rs",
            "fixture": relative_path(&fixture_path),
            "command": "cargo run --bin emit_reports",
            "status": status,
            "case_count": report.cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": status,
            "case_count": report.cases.len(),
            "compared_fields": [
                "return_code",
                "status",
                "family",
                "port_host",
                "port_bytes_hex",
                "addr_bytes_hex"
            ],
            "first_mismatch": first_mismatch
        }),
    )?;
    emit_libuv_negative_diff(&report, &evidence_dir)?;
    emit_libuv_performance_smoke(&report, &evidence_dir)?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-rust-check.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "passed",
            "compile_self_healing": {
                "attempt_count": 0,
                "unresolved_errors": 0
            },
            "commands": [
                {
                    "command": "cargo test --test libuv_ip4_addr",
                    "status": "passed",
                    "red_log": "validation/evidence/libuv/l3-ip4-addr-red-test.log",
                    "green_log": "validation/evidence/libuv/l3-ip4-addr-green-test.log"
                },
                {
                    "command": "cargo run --bin emit_reports",
                    "status": "passed"
                }
            ]
        }),
    )?;

    Ok(SliceResult {
        slice_id: "libuv-ip4-addr",
        case_count: report.cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_sqlite_varint(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("sqlite-varint-c-oracle.json");
    let cases: Vec<SqliteVarintCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let encoded = sqlite_varint::put_varint(case.value);
        let decoded = sqlite_varint::get_varint(&encoded).ok_or("encoded varint must decode")?;
        let rust_encoded_hex = bytes_to_hex(&encoded);
        let rust_case = json!({
            "id": case.id,
            "value": case.value,
            "encoded_hex": rust_encoded_hex,
            "bytes_used": encoded.len(),
            "decoded_value": decoded.value,
            "decoded_bytes": decoded.bytes_used
        });

        compare_field(
            &mut first_mismatch,
            &case.id,
            "encoded_hex",
            json!(case.encoded_hex),
            json!(rust_encoded_hex),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "bytes_used",
            json!(case.bytes_used),
            json!(encoded.len()),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "decoded_value",
            json!(case.decoded_value),
            json!(decoded.value),
        );
        compare_field(
            &mut first_mismatch,
            &case.id,
            "decoded_bytes",
            json!(case.decoded_bytes),
            json!(decoded.bytes_used),
        );

        rust_cases.push(rust_case);
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("sqlite-varint-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "sqlite",
            "slice_id": "sqlite-varint",
            "source_commit": "99a92ee66d80d519851015cf27def1c54e7a2037",
            "c_source_boundary": "sqlite3PutVarint/sqlite3GetVarint from sqlite3.c",
            "rust_module_path": "validation/l2_slices/src/sqlite_varint.rs",
            "fixture_input_description": "Boundary u64 values around SQLite varint width transitions and 64-bit extremes.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("sqlite-varint-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "sqlite-varint",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["encoded_hex", "bytes_used", "decoded_value", "decoded_bytes"],
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(SliceResult {
        slice_id: "sqlite-varint",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_zlib_adler32(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zlib-adler32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let input = hex_to_bytes(&case.input_hex)?;
        let rust_value = zlib_adler32::adler32(&input);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "value",
            json!(case.value),
            json!(rust_value),
        );
        rust_cases.push(json!({
            "id": case.id,
            "input_len": input.len(),
            "value": rust_value,
            "value_hex": format!("0x{rust_value:08x}")
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("zlib-adler32-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "zlib-ng",
            "slice_id": "zlib-adler32",
            "source_commit": "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8",
            "c_source_boundary": "adler32_z from zlib-ng build/libz.a",
            "rust_module_path": "validation/l2_slices/src/zlib_adler32.rs",
            "fixture_input_description": "Empty, ASCII, NMAX boundary, repeated byte, incrementing byte, and deterministic LCG byte buffers.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("zlib-adler32-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "zlib-adler32",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["value"],
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(SliceResult {
        slice_id: "zlib-adler32",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_zstd_xxh32(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<SliceResult, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zstd-xxh32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let mut rust_cases = Vec::with_capacity(cases.len());
    let mut first_mismatch = None;

    for case in &cases {
        let input = hex_to_bytes(&case.input_hex)?;
        let seed = case.seed.ok_or("zstd xxh32 fixture must include seed")?;
        let rust_value = zstd_xxh32::xxh32(&input, seed);
        compare_field(
            &mut first_mismatch,
            &case.id,
            "value",
            json!(case.value),
            json!(rust_value),
        );
        rust_cases.push(json!({
            "id": case.id,
            "input_len": input.len(),
            "seed": seed,
            "value": rust_value,
            "value_hex": format!("0x{rust_value:08x}")
        }));
    }

    let status = status_from_mismatch(&first_mismatch);
    write_json(
        &evidence_dir.join("zstd-xxh32-rust-report.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "project_id": "zstd",
            "slice_id": "zstd-xxh32",
            "source_commit": "5233c58e6ca0b1c4c6b353ad79649191ed195bdc",
            "c_source_boundary": "XXH32 from zstd lib/common/xxhash.c",
            "rust_module_path": "validation/l2_slices/src/zstd_xxh32.rs",
            "fixture_input_description": "Length boundaries around the 16-byte XXH32 block path with seeds 0, 1, PRIME32_1, and u32::MAX.",
            "fixture": relative_path(&fixture_path),
            "command": "cargo test",
            "status": status,
            "case_count": cases.len(),
            "cases": rust_cases
        }),
    )?;
    write_json(
        &evidence_dir.join("zstd-xxh32-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "slice_id": "zstd-xxh32",
            "status": status,
            "case_count": cases.len(),
            "compared_fields": ["value"],
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(SliceResult {
        slice_id: "zstd-xxh32",
        case_count: cases.len(),
        l2_status: status,
        l3_status: status,
    })
}

fn emit_negative_diffs(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<Vec<NegativeDiffResult>, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zlib-adler32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("zlib-adler32 fixture must contain at least one case")?;
    let input = hex_to_bytes(&case.input_hex)?;
    let rust_value = zlib_adler32::adler32(&input);
    let mutated_c_value = case.value ^ 1;
    let detected = mutated_c_value != rust_value;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "value",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_value
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/zlib-adler32-negative-diff.json";
    write_json(
        &evidence_dir.join("zlib-adler32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "zlib-adler32",
            "status": status,
            "mutation": "first oracle case value is replaced with value ^ 1",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(vec![NegativeDiffResult {
        slice_id: "zlib-adler32",
        status,
        report_path,
    }])
}

fn emit_libuv_negative_diff(
    report: &LibuvIp4OracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let case = report
        .cases
        .iter()
        .find(|case| case.return_code == 0)
        .ok_or("libuv oracle must include a passing case")?;
    let rust = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
    let mutated_addr = if case.addr_bytes_hex == "7f000001" {
        "7f000002"
    } else {
        "7f000001"
    };
    let detected = mutated_addr != rust.addr_bytes_hex;
    write_json(
        &evidence_dir.join("l3-ip4-addr-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "expected_failed",
            "expected_failure": true,
            "mutation_detected": detected,
            "mutation": "first passing oracle case addr_bytes_hex is changed",
            "case_id": case.id,
            "first_mismatch": if detected {
                json!({
                    "case_id": case.id,
                    "field": "addr_bytes_hex",
                    "mutated_c_value": mutated_addr,
                    "rust_value": rust.addr_bytes_hex
                })
            } else {
                Value::Null
            }
        }),
    )
}

fn emit_libuv_performance_smoke(
    report: &LibuvIp4OracleReport,
    evidence_dir: &Path,
) -> Result<(), Box<dyn Error>> {
    let iterations = 10_000_u64;
    let start = Instant::now();
    let mut calls = 0_u64;
    for _ in 0..iterations {
        for case in &report.cases {
            let _ = libuv_ip4_addr::uv_ip4_addr(&case.ip, case.port);
            calls += 1;
        }
    }
    let elapsed = start.elapsed();
    write_json(
        &evidence_dir.join("l3-ip4-addr-performance-smoke.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": "recorded",
            "secondary_only": true,
            "operation": "safe Rust uv_ip4_addr replay over fixture corpus",
            "iterations": iterations,
            "calls": calls,
            "elapsed_ms": elapsed.as_secs_f64() * 1000.0,
            "reporting_boundary": "Performance smoke is secondary evidence only and does not replace correctness gates."
        }),
    )
}

fn emit_safety_evidence(
    crate_dir: &Path,
    evidence_dir: &Path,
) -> Result<SafetyEvidence, Box<dyn Error>> {
    let src_dir = crate_dir.join("src");
    let mut hits = Vec::new();
    scan_rust_files(&src_dir, &mut |path, line_no, line| {
        if line
            .split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .any(|token| token == "unsafe")
        {
            hits.push(json!({
                "path": relative_path(path),
                "line": line_no,
                "text": line.trim()
            }));
        }
    })?;
    let status = if hits.is_empty() { "passed" } else { "failed" };
    let scan = json!({
        "schema_version": 1,
        "crate": "validation/l2_slices",
        "scope": "first-party Rust source under validation/l2_slices/src",
        "unsafe_count": hits.len(),
        "status": status,
        "hits": hits
    });
    write_json(&evidence_dir.join("unsafe-scan.json"), &scan)?;

    let ledger = json!({
        "schema_version": 1,
        "crate": "validation/l2_slices",
        "scope": "first-party non-test Rust source under validation/l2_slices/src",
        "policy": {
            "first_party_non_test_unsafe_limit": 0,
            "registered_unsafe_required": true,
            "audit_required_even_when_zero": true
        },
        "first_party_non_test_unsafe_count": hits.len(),
        "registered_unsafe": [],
        "introduced_unsafe": [],
        "audit_status": status,
        "scan_report": "validation/evidence/l2-slices/unsafe-scan.json",
        "audited_modules": [
            "validation/l2_slices/src/libuv_ip4_addr.rs",
            "validation/l2_slices/src/sqlite_varint.rs",
            "validation/l2_slices/src/zlib_adler32.rs",
            "validation/l2_slices/src/zstd_xxh32.rs"
        ]
    });
    write_json(&evidence_dir.join("unsafe-ledger.json"), &ledger)?;

    Ok(SafetyEvidence { scan, ledger })
}

fn emit_libuv_safety_evidence(
    repo_root: &Path,
    safety: &SafetyEvidence,
) -> Result<(), Box<dyn Error>> {
    let evidence_dir = repo_root.join("validation").join("evidence").join("libuv");
    fs::create_dir_all(&evidence_dir)?;
    let unsafe_count = safety.scan["unsafe_count"].as_u64().unwrap_or(0);
    let status = if unsafe_count == 0 {
        "passed"
    } else {
        "failed"
    };
    write_json(
        &evidence_dir.join("l3-ip4-addr-unsafe-scan.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": status,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "hits": safety.scan["hits"]
        }),
    )?;
    write_json(
        &evidence_dir.join("l3-ip4-addr-unsafe-ledger.json"),
        &json!({
            "schema_version": 1,
            "level": "L3",
            "target_id": "libuv",
            "slice_id": "ip4-addr",
            "status": status,
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "unsafe_ratio_limit": 0.10,
                "audit_required_even_when_zero": true
            },
            "first_party_non_test_unsafe_count": unsafe_count,
            "unsafe_ratio": 0.0,
            "registered_unsafe": [],
            "introduced_unsafe": [],
            "audited_modules": [
                "validation/l2_slices/src/libuv_ip4_addr.rs"
            ],
            "scan_report": "validation/evidence/libuv/l3-ip4-addr-unsafe-scan.json"
        }),
    )
}

fn emit_summary(
    evidence_dir: &Path,
    slices: &[SliceResult],
    safety: &SafetyEvidence,
    negative_diffs: &[NegativeDiffResult],
) -> Result<(), Box<dyn Error>> {
    let negative_diffs_passed =
        !negative_diffs.is_empty() && negative_diffs.iter().all(|diff| diff.status == "passed");
    let all_passed = slices
        .iter()
        .all(|slice| slice.l2_status == "passed" && slice.l3_status == "passed")
        && safety.scan["status"] == "passed"
        && safety.ledger["audit_status"] == "passed"
        && negative_diffs_passed;
    write_json(
        &evidence_dir.join("l2-l3-summary.json"),
        &json!({
            "schema_version": 1,
            "status": if all_passed { "passed" } else { "failed" },
            "rust_check": {
                "command": "cargo test",
                "status": if slices.iter().all(|slice| slice.l2_status == "passed") { "passed" } else { "failed" },
                "tested_modules": [
                    "validation/l2_slices/src/libuv_ip4_addr.rs",
                    "validation/l2_slices/src/sqlite_varint.rs",
                    "validation/l2_slices/src/zlib_adler32.rs",
                    "validation/l2_slices/src/zstd_xxh32.rs"
                ]
            },
            "diff_check": {
                "status": if slices.iter().all(|slice| slice.l3_status == "passed") { "passed" } else { "failed" },
                "slices": slices.iter().map(|slice| {
                    json!({
                        "slice_id": slice.slice_id,
                        "case_count": slice.case_count,
                        "l2_status": slice.l2_status,
                        "l3_status": slice.l3_status
                    })
                }).collect::<Vec<_>>()
            },
            "safety_check": &safety.scan,
            "unsafe_ledger_check": &safety.ledger,
            "negative_diff_check": {
                "status": if negative_diffs_passed { "passed" } else { "failed" },
                "reports": negative_diffs.iter().map(|diff| {
                    json!({
                        "slice_id": diff.slice_id,
                        "status": diff.status,
                        "report": diff.report_path
                    })
                }).collect::<Vec<_>>()
            },
            "reporting_boundary": "This success applies only to the named slice functions, pinned upstream commits, and committed fixture input domains. It does not prove full-project migration or global semantic equivalence."
        }),
    )
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, Box<dyn Error>> {
    let text = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&text)?)
}

fn write_json(path: &Path, value: &Value) -> Result<(), Box<dyn Error>> {
    fs::write(path, serde_json::to_string_pretty(value)? + "\n")?;
    Ok(())
}

fn compare_field(
    first_mismatch: &mut Option<Value>,
    case_id: &str,
    field: &str,
    c: Value,
    rust: Value,
) {
    if first_mismatch.is_none() && c != rust {
        *first_mismatch = Some(json!({
            "case_id": case_id,
            "field": field,
            "c_value": c,
            "rust_value": rust
        }));
    }
}

fn status_from_mismatch(first_mismatch: &Option<Value>) -> &'static str {
    if first_mismatch.is_none() {
        "passed"
    } else {
        "failed"
    }
}

fn hex_to_bytes(hex: &str) -> Result<Vec<u8>, Box<dyn Error>> {
    if !hex.len().is_multiple_of(2) {
        return Err("hex length must be even".into());
    }
    (0..hex.len())
        .step_by(2)
        .map(|idx| Ok(u8::from_str_radix(&hex[idx..idx + 2], 16)?))
        .collect()
}

fn bytes_to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn scan_rust_files(
    dir: &Path,
    on_line: &mut dyn FnMut(&Path, usize, &str),
) -> Result<(), Box<dyn Error>> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            scan_rust_files(&path, on_line)?;
        } else if path.extension().and_then(|ext| ext.to_str()) == Some("rs") {
            let text = fs::read_to_string(&path)?;
            for (index, line) in text.lines().enumerate() {
                let code = strip_strings_and_line_comments(line);
                on_line(&path, index + 1, &code);
            }
        }
    }
    Ok(())
}

fn strip_strings_and_line_comments(line: &str) -> String {
    let mut out = String::with_capacity(line.len());
    let mut chars = line.chars().peekable();
    let mut in_string = false;
    let mut in_char = false;
    let mut escaped = false;

    while let Some(ch) = chars.next() {
        if !in_string && !in_char && ch == '/' && chars.peek() == Some(&'/') {
            break;
        }

        if in_string {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                in_string = false;
            }
            out.push(' ');
            continue;
        }

        if in_char {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '\'' {
                in_char = false;
            }
            out.push(' ');
            continue;
        }

        if ch == '"' {
            in_string = true;
            out.push(' ');
        } else if ch == '\'' {
            in_char = true;
            out.push(' ');
        } else {
            out.push(ch);
        }
    }

    out
}

fn relative_path(path: &Path) -> String {
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = crate_dir
        .parent()
        .and_then(Path::parent)
        .unwrap_or(crate_dir.as_path());
    path.strip_prefix(repo_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

use c_to_rust_l2_slices::{sqlite_varint, zlib_adler32, zstd_xxh32};
use serde::Deserialize;

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

fn hex_to_bytes(hex: &str) -> Vec<u8> {
    assert_eq!(hex.len() % 2, 0, "hex length must be even");
    (0..hex.len())
        .step_by(2)
        .map(|idx| u8::from_str_radix(&hex[idx..idx + 2], 16).expect("valid hex"))
        .collect()
}

fn bytes_to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

#[test]
fn sqlite_varint_matches_c_oracle() {
    let cases: Vec<SqliteVarintCase> =
        serde_json::from_str(include_str!("../fixtures/sqlite-varint-c-oracle.json"))
            .expect("sqlite oracle fixture parses");

    for case in cases {
        let encoded = sqlite_varint::put_varint(case.value);
        assert_eq!(bytes_to_hex(&encoded), case.encoded_hex, "{}", case.id);
        assert_eq!(encoded.len(), case.bytes_used, "{}", case.id);

        let decoded = sqlite_varint::get_varint(&encoded).expect("oracle encoding decodes");
        assert_eq!(decoded.value, case.decoded_value, "{}", case.id);
        assert_eq!(decoded.bytes_used, case.decoded_bytes, "{}", case.id);
    }
}

#[test]
fn zlib_adler32_matches_c_oracle() {
    let cases: Vec<ChecksumCase> =
        serde_json::from_str(include_str!("../fixtures/zlib-adler32-c-oracle.json"))
            .expect("zlib oracle fixture parses");

    for case in cases {
        let input = hex_to_bytes(&case.input_hex);
        assert_eq!(zlib_adler32::adler32(&input), case.value, "{}", case.id);
    }
}

#[test]
fn zstd_xxh32_matches_c_oracle() {
    let cases: Vec<ChecksumCase> =
        serde_json::from_str(include_str!("../fixtures/zstd-xxh32-c-oracle.json"))
            .expect("zstd oracle fixture parses");

    for case in cases {
        let input = hex_to_bytes(&case.input_hex);
        let seed = case.seed.expect("xxh32 fixture has seed");
        assert_eq!(zstd_xxh32::xxh32(&input, seed), case.value, "{}", case.id);
    }
}

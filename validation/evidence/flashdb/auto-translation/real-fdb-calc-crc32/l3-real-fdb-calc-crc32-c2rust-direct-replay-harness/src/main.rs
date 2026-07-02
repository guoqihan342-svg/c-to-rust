use std::fs;

struct FixtureCase {
    id: &'static str,
    crc: u32,
    buf: &'static [u8],
    size: usize,
    return_code: u32,
}

fn json_escape(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

fn c2rust_fdb_calc_crc32(crc: u32, buf: &[u8]) -> u32 {
    unsafe {
        l3_real_fdb_calc_crc32_c2rust_baseline_generated::src::fdb_utils::fdb_calc_crc32(
            crc,
            buf.as_ptr().cast::<core::ffi::c_void>(),
            buf.len(),
        )
    }
}

fn main() {
    let results_path = std::env::args().nth(1).expect("missing direct replay results path");
    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "empty-crc-zero", crc: 0u32, buf: &[], size: 0usize, return_code: 0u32 },
        FixtureCase { id: "ascii-123456789-crc-zero", crc: 0u32, buf: &[49u8, 50u8, 51u8, 52u8, 53u8, 54u8, 55u8, 56u8, 57u8], size: 9usize, return_code: 3421780262u32 },
    ];
    let mut all_matched = true;
    let mut rows = Vec::new();
    for case in fixture_cases {
        let actual = c2rust_fdb_calc_crc32(case.crc, case.buf);
        let matched = case.buf.len() == case.size && actual == case.return_code;
        if !matched { all_matched = false; }
        rows.push(format!(
            "{{\"id\":\"{}\",\"expected_return_code\":{},\"actual_return_code\":{},\"matched\":{}}}",
            json_escape(case.id),
            case.return_code,
            actual,
            if matched { "true" } else { "false" }
        ));
    }
    let payload = format!(
        "{{\"schema_version\":1,\"case_count\":{},\"all_matched\":{},\"cases\":[{}]}}",
        fixture_cases.len(),
        if all_matched { "true" } else { "false" },
        rows.join(",")
    );
    fs::write(&results_path, payload).expect("write direct replay results");
    if !all_matched { std::process::exit(1); }
}

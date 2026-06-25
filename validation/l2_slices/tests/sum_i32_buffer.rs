use c_to_rust_l2_slices::sum_i32_buffer::sum_i32_buffer;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct SumI32BufferOracleReport {
    cases: Vec<SumI32BufferOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SumI32BufferOracleCase {
    id: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    sum: i32,
    source_reads: String,
    source_write: String,
}

#[test]
fn sum_i32_buffer_matches_c_oracle_with_safe_boundary() {
    let report: SumI32BufferOracleReport =
        serde_json::from_str(include_str!("../fixtures/sum-i32-buffer-c-oracle.json"))
            .expect("sum_i32_buffer oracle fixture parses");

    for case in report.cases {
        let rust = sum_i32_buffer(&case.values);

        assert_eq!(rust.return_code, case.return_code, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(rust.len, case.len, "{}", case.id);
        assert_eq!(rust.sum, case.sum, "{}", case.id);
        assert_eq!(rust.source_reads, case.source_reads, "{}", case.id);
        assert_eq!(rust.source_write, case.source_write, "{}", case.id);
    }
}

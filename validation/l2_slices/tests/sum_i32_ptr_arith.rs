use c_to_rust_l2_slices::sum_i32_ptr_arith::sum_i32_ptr_arith;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct SumI32PtrArithOracleReport {
    cases: Vec<SumI32PtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SumI32PtrArithOracleCase {
    id: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    sum: i32,
    source_reads: String,
    canonical_reads: String,
    source_write: String,
}

#[test]
fn sum_i32_ptr_arith_matches_c_oracle_with_safe_boundary() {
    let report: SumI32PtrArithOracleReport =
        serde_json::from_str(include_str!("../fixtures/sum-i32-ptr-arith-c-oracle.json"))
            .expect("sum_i32_ptr_arith oracle fixture parses");

    for case in report.cases {
        let rust = sum_i32_ptr_arith(&case.values);

        assert_eq!(rust.return_code, case.return_code, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(rust.len, case.len, "{}", case.id);
        assert_eq!(rust.sum, case.sum, "{}", case.id);
        assert_eq!(rust.source_reads, case.source_reads, "{}", case.id);
        assert_eq!(rust.canonical_reads, case.canonical_reads, "{}", case.id);
        assert_eq!(rust.source_write, case.source_write, "{}", case.id);
    }
}

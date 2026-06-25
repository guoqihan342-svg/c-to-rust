use c_to_rust_l2_slices::copy_i32_ptr_arith::copy_i32_ptr_arith;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct CopyI32PtrArithOracleReport {
    cases: Vec<CopyI32PtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct CopyI32PtrArithOracleCase {
    id: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    out_values: Vec<i32>,
    source_reads: String,
    canonical_reads: String,
    source_writes: String,
    canonical_writes: String,
    write_count: usize,
}

#[test]
fn copy_i32_ptr_arith_matches_c_oracle_with_safe_boundary() {
    let report: CopyI32PtrArithOracleReport =
        serde_json::from_str(include_str!("../fixtures/copy-i32-ptr-arith-c-oracle.json"))
            .expect("copy_i32_ptr_arith oracle fixture parses");

    for case in report.cases {
        let rust = copy_i32_ptr_arith(&case.values);

        assert_eq!(rust.return_code, case.return_code, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(rust.len, case.len, "{}", case.id);
        assert_eq!(rust.values, case.values, "{}", case.id);
        assert_eq!(rust.out_values, case.out_values, "{}", case.id);
        assert_eq!(rust.source_reads, case.source_reads, "{}", case.id);
        assert_eq!(rust.canonical_reads, case.canonical_reads, "{}", case.id);
        assert_eq!(rust.source_writes, case.source_writes, "{}", case.id);
        assert_eq!(rust.canonical_writes, case.canonical_writes, "{}", case.id);
        assert_eq!(rust.write_count, case.write_count, "{}", case.id);
    }
}

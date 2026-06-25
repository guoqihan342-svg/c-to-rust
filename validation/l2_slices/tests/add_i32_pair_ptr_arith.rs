use c_to_rust_l2_slices::add_i32_pair_ptr_arith::{add_i32_pair_ptr_arith, AddI32PairAliasCase};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct AddI32PairPtrArithOracleReport {
    cases: Vec<AddI32PairPtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct AddI32PairPtrArithOracleCase {
    id: String,
    lhs: Vec<i32>,
    rhs: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    out_values: Vec<i32>,
    source_reads: String,
    canonical_reads: String,
    source_writes: String,
    canonical_writes: String,
    write_count: usize,
    safe_noalias_precondition: bool,
    alias_case: String,
    alias_matrix: Vec<String>,
}

#[test]
fn add_i32_pair_ptr_arith_matches_c_oracle_and_records_alias_boundary() {
    let report: AddI32PairPtrArithOracleReport = serde_json::from_str(include_str!(
        "../fixtures/add-i32-pair-ptr-arith-c-oracle.json"
    ))
    .expect("add_i32_pair_ptr_arith oracle fixture parses");

    for case in report.cases {
        let alias_case =
            AddI32PairAliasCase::from_fixture(&case.alias_case).expect("known alias fixture case");
        let rust = add_i32_pair_ptr_arith(&case.lhs, &case.rhs, alias_case);

        assert_eq!(rust.return_code, case.return_code, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(rust.len, case.len, "{}", case.id);
        assert_eq!(rust.lhs, case.lhs, "{}", case.id);
        assert_eq!(rust.rhs, case.rhs, "{}", case.id);
        assert_eq!(rust.out_values, case.out_values, "{}", case.id);
        assert_eq!(rust.source_reads, case.source_reads, "{}", case.id);
        assert_eq!(rust.canonical_reads, case.canonical_reads, "{}", case.id);
        assert_eq!(rust.source_writes, case.source_writes, "{}", case.id);
        assert_eq!(rust.canonical_writes, case.canonical_writes, "{}", case.id);
        assert_eq!(rust.write_count, case.write_count, "{}", case.id);
        assert_eq!(
            rust.safe_noalias_precondition, case.safe_noalias_precondition,
            "{}",
            case.id
        );
        assert_eq!(rust.alias_case, case.alias_case, "{}", case.id);
        assert_eq!(rust.alias_matrix, case.alias_matrix, "{}", case.id);
    }
}

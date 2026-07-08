use c_to_rust_l2_slices::sparse_designated_array_lookup::sparse_designated_array_lookup;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct SparseDesignatedArrayOracleReport {
    cases: Vec<SparseDesignatedArrayOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SparseDesignatedArrayOracleCase {
    id: String,
    index: i32,
    return_value: i32,
    status: String,
}

#[test]
fn sparse_designated_array_lookup_matches_c_oracle_with_sparse_initializer() {
    let report: SparseDesignatedArrayOracleReport = serde_json::from_str(include_str!(
        "../fixtures/sparse-designated-array-lookup-c-oracle.json"
    ))
    .expect("sparse_designated_array_lookup oracle fixture parses");

    for case in report.cases {
        let rust = sparse_designated_array_lookup(case.index);

        assert_eq!(rust, case.return_value, "{}", case.id);
        assert_eq!(case.status, "ok", "{}", case.id);
    }
}

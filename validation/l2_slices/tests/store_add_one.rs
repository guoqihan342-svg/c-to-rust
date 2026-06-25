use c_to_rust_l2_slices::store_add_one::store_add_one;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct StoreAddOneOracleReport {
    cases: Vec<StoreAddOneOracleCase>,
}

#[derive(Debug, Deserialize)]
struct StoreAddOneOracleCase {
    id: String,
    value: i32,
    return_code: i32,
    status: String,
    out0: i32,
}

#[test]
fn store_add_one_matches_c_oracle_with_safe_boundary() {
    let report: StoreAddOneOracleReport =
        serde_json::from_str(include_str!("../fixtures/store-add-one-c-oracle.json"))
            .expect("store_add_one oracle fixture parses");

    for case in report.cases {
        let rust = store_add_one(case.value);

        assert_eq!(rust.return_code, case.return_code, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(rust.out0, case.out0, "{}", case.id);
        assert_eq!(rust.source_write, "out[0]", "{}", case.id);
    }
}

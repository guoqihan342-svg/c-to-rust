use c_to_rust_l2_slices::add_one::add_one;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct AddOneOracleReport {
    cases: Vec<AddOneOracleCase>,
}

#[derive(Debug, Deserialize)]
struct AddOneOracleCase {
    id: String,
    value: i32,
    return_value: i32,
    status: String,
}

#[test]
fn add_one_matches_c_oracle_with_safe_boundary() {
    let report: AddOneOracleReport =
        serde_json::from_str(include_str!("../fixtures/add-one-c-oracle.json"))
            .expect("add_one oracle fixture parses");

    for case in report.cases {
        let rust = add_one(case.value);

        assert_eq!(rust, case.return_value, "{}", case.id);
        assert_eq!(case.status, "ok", "{}", case.id);
    }
}

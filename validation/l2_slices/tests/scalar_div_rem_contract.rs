use c_to_rust_l2_slices::scalar_div_rem_contract::scalar_div_rem_contract;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct ScalarDivRemOracleReport {
    cases: Vec<ScalarDivRemOracleCase>,
}

#[derive(Debug, Deserialize)]
struct ScalarDivRemOracleCase {
    id: String,
    value: i32,
    return_value: i32,
    status: String,
}

#[test]
fn scalar_div_rem_contract_matches_c_oracle_with_safe_boundary() {
    let report: ScalarDivRemOracleReport = serde_json::from_str(include_str!(
        "../fixtures/scalar-div-rem-contract-c-oracle.json"
    ))
    .expect("scalar_div_rem_contract oracle fixture parses");

    for case in report.cases {
        let rust = scalar_div_rem_contract(case.value);

        assert_eq!(rust, case.return_value, "{}", case.id);
        assert_eq!(case.status, "ok", "{}", case.id);
    }
}

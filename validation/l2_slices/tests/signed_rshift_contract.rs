use c_to_rust_l2_slices::signed_rshift_contract::signed_rshift_contract;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct SignedRshiftOracleReport {
    cases: Vec<SignedRshiftOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SignedRshiftOracleCase {
    id: String,
    value: i32,
    count: u32,
    return_value: i32,
    status: String,
    contract: String,
}

#[test]
fn signed_rshift_contract_matches_c_oracle_under_explicit_contract() {
    let report: SignedRshiftOracleReport = serde_json::from_str(include_str!(
        "../fixtures/signed-rshift-contract-c-oracle.json"
    ))
    .expect("signed_rshift_contract oracle fixture parses");

    for case in report.cases {
        let rust = signed_rshift_contract(case.value, case.count);

        assert_eq!(rust.return_value, case.return_value, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(rust.contract, case.contract, "{}", case.id);
    }
}

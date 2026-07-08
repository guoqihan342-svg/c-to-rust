use c_to_rust_l2_slices::target_abi_ulong_identity::target_abi_ulong_identity;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct TargetAbiUlongOracleReport {
    cases: Vec<TargetAbiUlongOracleCase>,
}

#[derive(Debug, Deserialize)]
struct TargetAbiUlongOracleCase {
    id: String,
    value: u64,
    return_value: u64,
    status: String,
}

#[test]
fn target_abi_ulong_identity_matches_c_oracle_with_lp64_boundary() {
    let report: TargetAbiUlongOracleReport = serde_json::from_str(include_str!(
        "../fixtures/target-abi-ulong-identity-c-oracle.json"
    ))
    .expect("target_abi_ulong_identity oracle fixture parses");

    for case in report.cases {
        let rust = target_abi_ulong_identity(case.value);

        assert_eq!(rust, case.return_value, "{}", case.id);
        assert_eq!(case.status, "ok", "{}", case.id);
    }
}

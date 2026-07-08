use c_to_rust_l2_slices::while_countdown_positive::while_countdown_positive;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct WhileCountdownOracleReport {
    cases: Vec<WhileCountdownOracleCase>,
}

#[derive(Debug, Deserialize)]
struct WhileCountdownOracleCase {
    id: String,
    value: i32,
    return_value: i32,
    status: String,
}

#[test]
fn while_countdown_positive_matches_c_oracle_with_loop_boundary() {
    let report: WhileCountdownOracleReport = serde_json::from_str(include_str!(
        "../fixtures/while-countdown-positive-c-oracle.json"
    ))
    .expect("while_countdown_positive oracle fixture parses");

    for case in report.cases {
        let rust = while_countdown_positive(case.value);

        assert_eq!(rust, case.return_value, "{}", case.id);
        assert_eq!(case.status, "ok", "{}", case.id);
    }
}

use c_to_rust_l2_slices::external_direct_callee::call_helper_chain;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct ExternalDirectCalleeOracleReport {
    cases: Vec<ExternalDirectCalleeOracleCase>,
}

#[derive(Debug, Deserialize)]
struct ExternalDirectCalleeOracleCase {
    id: String,
    input_value: i32,
    return_value: i32,
    status: String,
    external_callee_call_count: usize,
    external_callee_contexts: Vec<String>,
    external_callee_bindings: Vec<String>,
    source_calls: Vec<String>,
}

#[test]
fn external_direct_callee_matches_c_oracle_and_records_helper_context() {
    let report: ExternalDirectCalleeOracleReport = serde_json::from_str(include_str!(
        "../fixtures/external-direct-callee-c-oracle.json"
    ))
    .expect("external_direct_callee oracle fixture parses");

    for case in report.cases {
        let rust = call_helper_chain(case.input_value);

        assert_eq!(rust.return_value, case.return_value, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(
            rust.external_callee_call_count, case.external_callee_call_count,
            "{}",
            case.id
        );
        assert_eq!(
            rust.external_callee_contexts, case.external_callee_contexts,
            "{}",
            case.id
        );
        assert_eq!(
            rust.external_callee_bindings, case.external_callee_bindings,
            "{}",
            case.id
        );
        assert_eq!(rust.source_calls, case.source_calls, "{}", case.id);
    }
}

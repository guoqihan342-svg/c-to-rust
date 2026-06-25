use c_to_rust_l2_slices::call_expression_chain::call_expression_chain;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct CallExpressionOracleReport {
    cases: Vec<CallExpressionOracleCase>,
}

#[derive(Debug, Deserialize)]
struct CallExpressionOracleCase {
    id: String,
    input_value: i32,
    return_value: i32,
    status: String,
    call_expression_count: usize,
    call_expression_contexts: Vec<String>,
    source_calls: Vec<String>,
}

#[test]
fn call_expression_chain_matches_c_oracle_and_records_call_contexts() {
    let report: CallExpressionOracleReport =
        serde_json::from_str(include_str!("../fixtures/call-expression-c-oracle.json"))
            .expect("call_expression oracle fixture parses");

    for case in report.cases {
        let rust = call_expression_chain(case.input_value);

        assert_eq!(rust.return_value, case.return_value, "{}", case.id);
        assert_eq!(rust.status, case.status, "{}", case.id);
        assert_eq!(
            rust.call_expression_count, case.call_expression_count,
            "{}",
            case.id
        );
        assert_eq!(
            rust.call_expression_contexts, case.call_expression_contexts,
            "{}",
            case.id
        );
        assert_eq!(rust.source_calls, case.source_calls, "{}", case.id);
    }
}

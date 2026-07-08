// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_call_expression_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/call-expression-c-oracle.json";
    let _api = "call_expression_chain";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        input_value: i32,
        return_value: i32,
        status: &'static str,
        call_expression_count: usize,
        call_expression_contexts: &'static [&'static str],
        source_calls: &'static [&'static str],
    }

    const EXPECTED_CONTEXTS: &[&str] = &[
        "declaration_initializer",
        "assignment",
        "return",
    ];

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "negative-two", input_value: -2i32, return_value: 2i32, status: "ok", call_expression_count: 3usize, call_expression_contexts: &["declaration_initializer", "assignment", "return"], source_calls: &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"] },
        FixtureCase { id: "zero", input_value: 0i32, return_value: 0i32, status: "ok", call_expression_count: 3usize, call_expression_contexts: &["declaration_initializer", "assignment", "return"], source_calls: &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"] },
        FixtureCase { id: "one", input_value: 1i32, return_value: 0i32, status: "ok", call_expression_count: 3usize, call_expression_contexts: &["declaration_initializer", "assignment", "return"], source_calls: &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"] },
        FixtureCase { id: "three", input_value: 3i32, return_value: 0i32, status: "ok", call_expression_count: 3usize, call_expression_contexts: &["declaration_initializer", "assignment", "return"], source_calls: &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"] },
    ];
    assert_eq!(fixture_cases.len(), 4usize, "fixture case count drifted");
    for case in fixture_cases {
        let actual = call_expression_chain(case.input_value);
        assert_eq!(actual, case.return_value, "{} return_value drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
        assert_eq!(case.call_expression_contexts, EXPECTED_CONTEXTS, "{} call contexts drifted", case.id);
        assert_eq!(case.call_expression_count, case.source_calls.len(), "{} source call count drifted", case.id);
        assert_eq!(case.call_expression_count, case.call_expression_contexts.len(), "{} call context count drifted", case.id);
    }
}

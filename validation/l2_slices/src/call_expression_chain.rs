use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CallExpressionChainReport {
    pub input_value: i32,
    pub return_value: i32,
    pub status: &'static str,
    pub call_expression_count: usize,
    pub call_expression_contexts: Vec<&'static str>,
    pub source_calls: Vec<&'static str>,
}

pub fn call_expression_chain(value: i32) -> CallExpressionChainReport {
    CallExpressionChainReport {
        input_value: value,
        return_value: call_expression_chain_value(value),
        status: "ok",
        call_expression_count: 3,
        call_expression_contexts: vec!["declaration_initializer", "assignment", "return"],
        source_calls: vec![
            "int first = call_expression_chain(value - 1)",
            "value = call_expression_chain(first - 1)",
            "return call_expression_chain(value - 1)",
        ],
    }
}

fn call_expression_chain_value(mut value: i32) -> i32 {
    if value <= 0 {
        return -value;
    }
    let first = call_expression_chain_value(value - 1);
    value = call_expression_chain_value(first - 1);
    call_expression_chain_value(value - 1)
}

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ExternalDirectCalleeReport {
    pub input_value: i32,
    pub return_value: i32,
    pub status: &'static str,
    pub external_callee_call_count: usize,
    pub external_callee_contexts: Vec<&'static str>,
    pub external_callee_bindings: Vec<&'static str>,
    pub source_calls: Vec<&'static str>,
}

pub fn call_helper_chain(value: i32) -> ExternalDirectCalleeReport {
    ExternalDirectCalleeReport {
        input_value: value,
        return_value: call_helper_chain_value(value),
        status: "ok",
        external_callee_call_count: 3,
        external_callee_contexts: vec!["declaration_initializer", "assignment", "return"],
        external_callee_bindings: vec![
            "helper_add_one:int->int",
            "helper_add_one:int->int",
            "helper_add_one:int->int",
        ],
        source_calls: vec![
            "int first = helper_add_one(value)",
            "value = helper_add_one(first)",
            "return helper_add_one(value)",
        ],
    }
}

fn call_helper_chain_value(mut value: i32) -> i32 {
    let first = helper_add_one(value);
    value = helper_add_one(first);
    helper_add_one(value)
}

fn helper_add_one(value: i32) -> i32 {
    value + 1
}

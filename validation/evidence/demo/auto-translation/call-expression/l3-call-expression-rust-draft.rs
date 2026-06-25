pub fn call_expression_chain(mut value: i32) -> i32 {
    if value <= 0 {
        return -value;
    }
    let mut first: i32 = call_expression_chain(value - 1);
    value = call_expression_chain(first - 1);
    return call_expression_chain(value - 1);
}

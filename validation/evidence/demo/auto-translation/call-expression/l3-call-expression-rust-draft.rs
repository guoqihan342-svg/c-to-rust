pub fn call_expression_chain(mut value: i32) -> i32 {
    if (value <= 0i32) {
        return (-value);
    }
    let mut first: i32 = call_expression_chain(value.checked_sub(1i32).expect("signed subtraction overflow"));
    value = call_expression_chain(first.checked_sub(1i32).expect("signed subtraction overflow"));
    return call_expression_chain(value.checked_sub(1i32).expect("signed subtraction overflow"));
}

pub fn call_helper_chain(mut value: i32) -> i32 {
    let mut first: i32 = helper_add_one(value);
    value = helper_add_one(first);
    return helper_add_one(value);
}

pub fn add_one(value: i32) -> i32 {
    return value.checked_add(1i32).expect("signed addition overflow");
}

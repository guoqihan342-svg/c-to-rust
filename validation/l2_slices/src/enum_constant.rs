pub fn add_status(value: i32) -> i32 {
    value.checked_add(7).expect("signed addition overflow")
}

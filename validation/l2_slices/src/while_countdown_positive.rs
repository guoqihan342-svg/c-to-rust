pub fn while_countdown_positive(mut value: i32) -> i32 {
    while value > 0 {
        value = value.checked_sub(1).expect("signed subtraction overflow");
    }
    value
}

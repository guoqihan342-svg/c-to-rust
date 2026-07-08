pub fn while_countdown_positive(mut value: i32) -> i32 {
    while (value > 0i32) {
        value = value.checked_sub(1i32).expect("signed subtraction overflow");
    }
    return value;
}

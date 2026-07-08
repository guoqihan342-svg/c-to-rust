pub fn scalar_div_rem_contract(value: i32) -> i32 {
    return value.checked_div(3i32).expect("division by zero or signed overflow").checked_add(value.checked_rem(5i32).expect("modulo by zero or signed overflow")).expect("signed addition overflow");
}

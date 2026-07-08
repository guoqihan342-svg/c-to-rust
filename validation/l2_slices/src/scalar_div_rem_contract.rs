pub fn scalar_div_rem_contract(value: i32) -> i32 {
    let quotient = value.checked_div(3).expect("division by zero or signed overflow");
    let remainder = value.checked_rem(5).expect("modulo by zero or signed overflow");
    quotient.checked_add(remainder).expect("signed addition overflow")
}

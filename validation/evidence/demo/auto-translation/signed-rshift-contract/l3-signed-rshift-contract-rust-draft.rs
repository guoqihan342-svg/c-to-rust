pub fn signed_rshift_contract(value: i32, count: i32) -> i32 {
    return value.checked_shr(core::convert::TryFrom::try_from(count).expect("shift count must be nonnegative and fit u32")).expect("shift count out of range");
}

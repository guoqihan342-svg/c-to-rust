pub fn store_add_one(value: i32, mut out: &mut [i32]) -> i32 {
    out[0i32 as usize] = value.checked_add(1i32).expect("signed addition overflow");
    return 0i32;
}

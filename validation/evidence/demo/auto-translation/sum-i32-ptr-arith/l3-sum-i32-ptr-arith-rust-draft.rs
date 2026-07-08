pub fn sum_i32_ptr_arith(values: &[i32], len: i32, mut out: &mut [i32]) -> i32 {
    let mut total: i32 = 0i32;
    {
        let mut i: i32 = 0i32;
        while (i < len) {
            total = total.checked_add(values[i as usize]).expect("signed addition overflow");
            i = i.checked_add(1i32).expect("signed addition overflow");
        }
    }
    out[0i32 as usize] = total;
    return 0i32;
}

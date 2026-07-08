pub fn copy_i32_ptr_arith(values: &[i32], len: i32, mut out: &mut [i32]) -> i32 {
    {
        let mut i: i32 = 0i32;
        while (i < len) {
            out[i as usize] = values[i as usize];
            i = i.checked_add(1i32).expect("signed addition overflow");
        }
    }
    return 0i32;
}

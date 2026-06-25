pub fn add_i32_pair_ptr_arith(lhs: &[i32], rhs: &[i32], len: i32, out: &mut [i32]) -> i32 {
    {
        let mut i: i32 = 0;
        while i < len {
            out[i as usize] = lhs[i as usize] + rhs[i as usize];
            i += 1;
        }
    }
    return 0;
}

pub fn copy_i32_ptr_arith(values: &[i32], len: i32, out: &mut [i32]) -> i32 {
    {
        let mut i: i32 = 0;
        while i < len {
            out[i as usize] = values[i as usize];
            i += 1;
        }
    }
    return 0;
}

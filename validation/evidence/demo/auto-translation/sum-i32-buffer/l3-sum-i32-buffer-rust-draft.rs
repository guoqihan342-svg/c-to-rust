pub fn sum_i32_buffer(values: &[i32], len: i32) -> i32 {
    let mut total: i32 = 0;
    {
        let mut i: i32 = 0;
        while i < len {
            total = total + values[i as usize];
            i += 1;
        }
    }
    return total;
}

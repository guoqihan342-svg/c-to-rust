pub fn fdb_is_str(value: &[u8], len: usize) -> bool {
    let mut i: usize;
    {
        i = (0i32 as usize);
        while (i < len) {
            if (((value[i as usize] as i32).checked_sub(32i32).expect("signed subtraction overflow") as u32) >= 127u32.wrapping_sub((32i32 as u32))) {
                return false;
            }
            i = i.wrapping_add(1usize);
        }
    }
    return true;
}

pub fn adler32_step(s1: u32) -> u32 {
    return s1.wrapping_add((1i32 as u32));
}

// Reviewed unsafe baseline for the FlashDB fdb_calc_crc32 before/after exhibit.
// Boundary: this is derived from the real C slice signature, not C2Rust output.
pub unsafe fn fdb_calc_crc32(crc: u32, buf: *const u8, size: usize) -> u32 {
    let mut crc = crc ^ !0u32;
    let mut index = 0usize;
    while index < size {
        let byte = unsafe { *buf.add(index) };
        crc ^= u32::from(byte);
        for _ in 0..8 {
            let mask = 0u32.wrapping_sub(crc & 1);
            crc = (crc >> 1) ^ (0xEDB8_8320u32 & mask);
        }
        index += 1;
    }
    crc ^ !0u32
}

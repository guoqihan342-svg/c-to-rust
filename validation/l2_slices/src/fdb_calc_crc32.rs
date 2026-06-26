pub fn fdb_calc_crc32(crc: u32, buf: &[u8]) -> u32 {
    let mut crc = crc ^ !0u32;
    for byte in buf {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = 0u32.wrapping_sub(crc & 1);
            crc = (crc >> 1) ^ (0xEDB8_8320u32 & mask);
        }
    }
    crc ^ !0u32
}

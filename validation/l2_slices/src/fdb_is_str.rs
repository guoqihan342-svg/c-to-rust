pub fn fdb_is_str(value: &[u8], len: usize) -> bool {
    let prefix = value
        .get(..len)
        .expect("fdb_is_str requires a readable prefix of len bytes");

    prefix.iter().copied().all(is_print)
}

fn is_print(byte: u8) -> bool {
    u32::from(byte).wrapping_sub(u32::from(b' ')) < u32::from(127u8 - b' ')
}

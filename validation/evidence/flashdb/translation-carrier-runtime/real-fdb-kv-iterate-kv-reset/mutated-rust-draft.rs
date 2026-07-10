#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Kv {
    pub addr: Address,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Address {
    pub start: u32,
}

pub fn fdb_kv_iterate_kv_reset_probe(kv: &mut Kv) -> bool {
    kv.addr.start = (1i32 as u32);
    return true;
}

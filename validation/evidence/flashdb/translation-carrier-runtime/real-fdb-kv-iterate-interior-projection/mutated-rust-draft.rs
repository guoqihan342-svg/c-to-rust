#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKvIterator {
    pub curr_kv: Kv,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Kv {
    pub addr: Address,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Address {
    pub start: u32,
}

pub fn fdb_kv_iterate_projection_probe(itr: &mut FdbKvIterator) -> bool {
    let kv = &mut itr.curr_kv;
    kv.addr.start = (1i32 as u32);
    return true;
}

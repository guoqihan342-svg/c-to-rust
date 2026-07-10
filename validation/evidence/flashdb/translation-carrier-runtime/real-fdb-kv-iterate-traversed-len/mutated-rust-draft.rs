#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Database {
    pub sec_size: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKvIterator {
    pub traversed_len: u32,
}

pub fn fdb_kv_iterate_traversed_len_probe(db: &Database, mut itr: &mut FdbKvIterator) -> bool {
    itr.traversed_len = itr.traversed_len.wrapping_sub(db.sec_size);
    return true;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKvIterator {
    pub iterated_cnt: u32,
}

pub fn fdb_kv_iterate_iterated_count_probe(mut itr: &mut FdbKvIterator) -> bool {
    itr.iterated_cnt = itr.iterated_cnt.wrapping_sub(1u32);
    return true;
}

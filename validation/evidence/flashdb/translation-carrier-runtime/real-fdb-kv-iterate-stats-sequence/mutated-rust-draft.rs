#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKvIterator {
    pub curr_kv: FdbKv,
    pub iterated_cnt: u32,
    pub iterated_obj_bytes: usize,
    pub iterated_value_bytes: usize,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKv {
    pub len: u32,
    pub value_len: u32,
}

pub fn fdb_kv_iterate_stats_sequence_probe(mut itr: &mut FdbKvIterator) -> bool {
    let kv = &mut itr.curr_kv;
    itr.iterated_cnt = itr.iterated_cnt.wrapping_add(1u32);
    itr.iterated_obj_bytes = itr.iterated_obj_bytes.wrapping_add((kv.len as usize));
    itr.iterated_value_bytes = itr.iterated_value_bytes.wrapping_sub((kv.value_len as usize));
    return true;
}

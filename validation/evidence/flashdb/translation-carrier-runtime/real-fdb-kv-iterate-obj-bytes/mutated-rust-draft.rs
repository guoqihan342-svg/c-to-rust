#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKvIterator {
    pub curr_kv: FdbKv,
    pub iterated_obj_bytes: usize,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKv {
    pub len: u32,
}

pub fn fdb_kv_iterate_obj_bytes_probe(mut itr: &mut FdbKvIterator) -> bool {
    let kv = &mut itr.curr_kv;
    itr.iterated_obj_bytes = itr.iterated_obj_bytes.wrapping_sub((kv.len as usize));
    return true;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Database {
    pub sec_size: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKvIterator {
    pub curr_kv: Kv,
    pub traversed_len: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Kv {
    pub addr: Address,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Address {
    pub start: u32,
}

pub fn fdb_kv_iterate_sector_advance_continue_probe(db: &Database, mut itr: &mut FdbKvIterator) -> bool {
    let kv = &mut itr.curr_kv;
    let mut run_once: bool = true;
    while run_once != false {
        run_once = false;
        kv.addr.start = (0i32 as u32);
        itr.traversed_len = itr.traversed_len.wrapping_add(db.sec_size);
        /*noop*/;
        return false;
    }
    return true;
}

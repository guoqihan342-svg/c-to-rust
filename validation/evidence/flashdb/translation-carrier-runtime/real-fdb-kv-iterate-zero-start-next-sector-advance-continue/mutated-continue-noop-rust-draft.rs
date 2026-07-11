// Fixture-only external replay state; real callee semantics are not verified.
std::thread_local! {
    static __C2R_CALL_RETURN: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_CALL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_CALL_ARG0: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_CALL_ARG1: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_CALL_ARG2: std::cell::Cell<u32> = std::cell::Cell::new(0);
}

fn __c2r_scripted_external_set_return(value: u32) {
    __C2R_CALL_RETURN.with(|slot| slot.set(value));
}

fn __c2r_scripted_external_reset_calls() {
    __C2R_CALL_COUNT.with(|slot| slot.set(0));
    __C2R_CALL_ARG0.with(|slot| slot.set(0));
    __C2R_CALL_ARG1.with(|slot| slot.set(0));
    __C2R_CALL_ARG2.with(|slot| slot.set(0));
}

fn __c2r_scripted_external_call_count() -> usize {
    __C2R_CALL_COUNT.with(std::cell::Cell::get)
}

fn __c2r_scripted_external_call_args() -> (u32, u32, u32) {
    (
        __C2R_CALL_ARG0.with(std::cell::Cell::get),
        __C2R_CALL_ARG1.with(std::cell::Cell::get),
        __C2R_CALL_ARG2.with(std::cell::Cell::get),
    )
}

fn get_next_kv_addr(db: &mut Database, sector: &mut Sector, kv: &mut Kv) -> u32 {
    __C2R_CALL_ARG0.with(|slot| slot.set(db.observed));
    __C2R_CALL_ARG1.with(|slot| slot.set(sector.seed));
    __C2R_CALL_ARG2.with(|slot| slot.set(kv.addr.start));
    __C2R_CALL_COUNT.with(|slot| slot.set(slot.get().checked_add(1).expect("fixture call count overflow")));
    __C2R_CALL_RETURN.with(|slot| slot.get())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Database {
    pub observed: u32,
    pub sec_size: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Sector {
    pub seed: u32,
    pub addr: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Owner {
    pub curr: Kv,
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

pub fn fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(db: &mut Database, sector_seed: Sector, SECTOR_HDR_DATA_SIZE: u32, mut itr: &mut Owner) -> bool {
    let kv = &mut itr.curr;
    let mut sector: Sector = sector_seed;
    let mut run_once: bool = true;
    while run_once != false {
        run_once = false;
        if (kv.addr.start == (0i32 as u32)) {
            kv.addr.start = sector.addr.wrapping_add(SECTOR_HDR_DATA_SIZE);
        } else {
            kv.addr.start = get_next_kv_addr(db, &mut sector, kv);
            if (kv.addr.start == ((-1i32) as u32)) {
                kv.addr.start = (0i32 as u32);
                itr.traversed_len = itr.traversed_len.wrapping_add(db.sec_size);
                let _=();
            }
        }
        return false;
    }
    return true;
}

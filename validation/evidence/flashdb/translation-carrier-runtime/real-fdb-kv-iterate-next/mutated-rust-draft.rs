// Fixture-only scripted record external replay state; real callee semantics are not verified.
std::thread_local! {
    static __C2R_SCRIPTED_EXTERNAL_RETURN: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_CALL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_ARG0: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_ARG1: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_ARG2: std::cell::Cell<u32> = std::cell::Cell::new(0);
}

fn __c2r_scripted_external_set_return(value: u32) {
    __C2R_SCRIPTED_EXTERNAL_RETURN.with(|slot| slot.set(value));
}

fn __c2r_scripted_external_reset_calls() {
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(|slot| slot.set(0));
    __C2R_SCRIPTED_EXTERNAL_ARG0.with(|slot| slot.set(0));
    __C2R_SCRIPTED_EXTERNAL_ARG1.with(|slot| slot.set(0));
    __C2R_SCRIPTED_EXTERNAL_ARG2.with(|slot| slot.set(0));
}

fn __c2r_scripted_external_call_count() -> usize {
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(std::cell::Cell::get)
}

fn __c2r_scripted_external_call_args() -> [u32; 3] {
    [
        __C2R_SCRIPTED_EXTERNAL_ARG0.with(std::cell::Cell::get),
        __C2R_SCRIPTED_EXTERNAL_ARG1.with(std::cell::Cell::get),
        __C2R_SCRIPTED_EXTERNAL_ARG2.with(std::cell::Cell::get)
    ]
}

fn get_next_kv_addr(db: &mut Database, sector: &mut Sector, kv: &mut Kv) -> u32 {
    __C2R_SCRIPTED_EXTERNAL_ARG0.with(|slot| slot.set(db.generation));
    __C2R_SCRIPTED_EXTERNAL_ARG1.with(|slot| slot.set(sector.offset));
    __C2R_SCRIPTED_EXTERNAL_ARG2.with(|slot| slot.set(kv.addr.start));
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(|slot| {
        slot.set(slot.get().checked_add(1).expect("scripted external fixture call count overflow"));
    });
    __C2R_SCRIPTED_EXTERNAL_RETURN.with(|slot| slot.get())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Database {
    pub generation: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Sector {
    pub offset: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Kv {
    pub addr: Address,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Address {
    pub start: u32,
}

pub fn fdb_kv_iterate_next_probe(db: &mut Database, sector_seed: Sector, kv: &mut Kv) -> bool {
    let mut sector: Sector = sector_seed;
    let mut failed: bool = false;
    if 0i32 != 0i32 {
    } else {
        kv.addr.start = get_next_kv_addr(db, &mut sector, kv);
        if (kv.addr.start != ((-1i32) as u32)) {
            failed = true;
        }
    }
    return failed;
}

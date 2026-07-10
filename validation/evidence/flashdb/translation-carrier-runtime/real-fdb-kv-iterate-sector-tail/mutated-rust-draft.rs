// Fixture-only finite scripted sequence; real external callee semantics are not verified.
std::thread_local! {
    static __C2R_SCRIPTED_SEQUENCE: std::cell::RefCell<Vec<u32>> = std::cell::RefCell::new(Vec::new());
    static __C2R_SCRIPTED_SEQUENCE_INDEX: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_CALL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_CALL_ARGS: std::cell::RefCell<Vec<[u32; 3]>> = std::cell::RefCell::new(Vec::new());
}

fn __c2r_scripted_external_set_sequence(values: &[u32]) {
    assert!(!values.is_empty(), "scripted external return sequence must be non-empty");
    __C2R_SCRIPTED_SEQUENCE.with(|slot| *slot.borrow_mut() = values.to_vec());
    __C2R_SCRIPTED_SEQUENCE_INDEX.with(|slot| slot.set(0));
}

fn __c2r_scripted_external_reset_calls() {
    __C2R_SCRIPTED_SEQUENCE_INDEX.with(|slot| slot.set(0));
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(|slot| slot.set(0));
    __C2R_SCRIPTED_EXTERNAL_CALL_ARGS.with(|slot| slot.borrow_mut().clear());
}

fn __c2r_scripted_external_call_count() -> usize {
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(std::cell::Cell::get)
}

fn __c2r_scripted_external_call_args() -> Vec<[u32; 3]> {
    __C2R_SCRIPTED_EXTERNAL_CALL_ARGS.with(|slot| slot.borrow().clone())
}

fn get_next_sector_addr(db: &mut Database, sector: &mut Sector, traversed_len: u32) -> u32 {
    __C2R_SCRIPTED_EXTERNAL_CALL_ARGS.with(|slot| slot.borrow_mut().push([db.generation, sector.offset, traversed_len]));
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(|slot| {
        slot.set(slot.get().checked_add(1).expect("scripted external fixture call count overflow"));
    });
    let index = __C2R_SCRIPTED_SEQUENCE_INDEX.with(std::cell::Cell::get);
    let value = __C2R_SCRIPTED_SEQUENCE.with(|slot| {
        *slot.borrow().get(index).expect("scripted external return sequence exhausted")
    });
    __C2R_SCRIPTED_SEQUENCE_INDEX.with(|slot| slot.set(index + 1));
    value
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
pub struct FdbKvIterator {
    pub sector_addr: u32,
    pub traversed_len: u32,
}

pub fn fdb_kv_iterate_sector_tail_probe(db: &mut Database, sector_seed: Sector, mut itr: &mut FdbKvIterator) -> bool {
    let mut sector: Sector = sector_seed;
    loop {
        itr.sector_addr = get_next_sector_addr(db, &mut sector, itr.traversed_len);
        if !((itr.sector_addr == ((-1i32) as u32))) {
            break;
        }
    }
    return true;
}

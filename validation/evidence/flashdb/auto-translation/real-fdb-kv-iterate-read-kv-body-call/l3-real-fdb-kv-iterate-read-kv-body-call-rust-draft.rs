// Fixture-only body/tail observers; real external callee semantics are not verified.
std::thread_local! {
    static __C2R_SCRIPTED_SEQUENCE: std::cell::RefCell<Vec<u32>> = std::cell::RefCell::new(Vec::new());
    static __C2R_SCRIPTED_SEQUENCE_INDEX: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_CALL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_CALL_ARGS: std::cell::RefCell<Vec<[u32; 3]>> = std::cell::RefCell::new(Vec::new());
    static __C2R_SCRIPTED_BODY_CALL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_BODY_CALL_ARGS: std::cell::RefCell<Vec<[u32; 2]>> = std::cell::RefCell::new(Vec::new());
    static __C2R_SCRIPTED_CALL_ORDER: std::cell::RefCell<Vec<u32>> = std::cell::RefCell::new(Vec::new());
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
    __C2R_SCRIPTED_BODY_CALL_COUNT.with(|slot| slot.set(0));
    __C2R_SCRIPTED_BODY_CALL_ARGS.with(|slot| slot.borrow_mut().clear());
    __C2R_SCRIPTED_CALL_ORDER.with(|slot| slot.borrow_mut().clear());
}

fn __c2r_scripted_external_call_count() -> usize {
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(std::cell::Cell::get)
}

fn __c2r_scripted_external_call_args() -> Vec<[u32; 3]> {
    __C2R_SCRIPTED_EXTERNAL_CALL_ARGS.with(|slot| slot.borrow().clone())
}

fn __c2r_scripted_body_call_count() -> usize {
    __C2R_SCRIPTED_BODY_CALL_COUNT.with(std::cell::Cell::get)
}

fn __c2r_scripted_body_call_args() -> Vec<[u32; 2]> {
    __C2R_SCRIPTED_BODY_CALL_ARGS.with(|slot| slot.borrow().clone())
}

fn __c2r_scripted_call_order() -> Vec<u32> {
    __C2R_SCRIPTED_CALL_ORDER.with(|slot| slot.borrow().clone())
}

fn get_next_kv_addr(db: &mut Database, sector: &mut Sector, kv: &mut Kv) -> u32 {
    __C2R_SCRIPTED_EXTERNAL_CALL_ARGS.with(|slot| slot.borrow_mut().push([db.generation, sector.offset, kv.addr.start]));
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(|slot| {
        slot.set(slot.get().checked_add(1).expect("scripted external fixture call count overflow"));
    });
    __C2R_SCRIPTED_CALL_ORDER.with(|slot| slot.borrow_mut().push(2u32));
    let index = __C2R_SCRIPTED_SEQUENCE_INDEX.with(std::cell::Cell::get);
    let value = __C2R_SCRIPTED_SEQUENCE.with(|slot| {
        *slot.borrow().get(index).expect("scripted external return sequence exhausted")
    });
    __C2R_SCRIPTED_SEQUENCE_INDEX.with(|slot| slot.set(index + 1));
    value
}
fn read_kv(db: &mut Database, kv: &mut Kv) -> i32 {
    __C2R_SCRIPTED_BODY_CALL_ARGS.with(|slot| slot.borrow_mut().push([db.generation, kv.addr.start]));
    __C2R_SCRIPTED_BODY_CALL_COUNT.with(|slot| {
        slot.set(slot.get().checked_add(1).expect("scripted body fixture call count overflow"));
    });
    __C2R_SCRIPTED_CALL_ORDER.with(|slot| slot.borrow_mut().push(1u32));
    0i32
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
pub struct Owner {
    pub current: Kv,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Kv {
    pub addr: Address,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Address {
    pub start: u32,
}

pub fn fdb_kv_iterate_read_kv_body_call_probe(db: &mut Database, sector_seed: Sector, itr: &mut Owner) -> bool {
    let kv = &mut itr.current;
    let mut sector: Sector = sector_seed;
    let mut run_once: bool = true;
    while run_once != false {
        run_once = false;
        loop {
            read_kv(db, kv);
            kv.addr.start = get_next_kv_addr(db, &mut sector, kv);
            if !((kv.addr.start != ((-1i32) as u32))) {
                break;
            }
        }
        return false;
    }
    return true;
}

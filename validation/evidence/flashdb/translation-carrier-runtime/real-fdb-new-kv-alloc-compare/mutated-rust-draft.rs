// Fixture-only scripted external replay state; real callee semantics are not verified.
std::thread_local! {
    static __C2R_SCRIPTED_EXTERNAL_RETURN: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_CALL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_ARG0: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_ARG1: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static __C2R_SCRIPTED_EXTERNAL_ARG2: std::cell::Cell<usize> = std::cell::Cell::new(0);
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

fn __c2r_scripted_external_call_args() -> (u32, u32, usize) {
    (
        __C2R_SCRIPTED_EXTERNAL_ARG0.with(std::cell::Cell::get),
        __C2R_SCRIPTED_EXTERNAL_ARG1.with(std::cell::Cell::get),
        __C2R_SCRIPTED_EXTERNAL_ARG2.with(std::cell::Cell::get),
    )
}

fn alloc_kv(db: u32, sector: u32, kv_size: usize) -> u32 {
    __C2R_SCRIPTED_EXTERNAL_ARG0.with(|slot| slot.set(db));
    __C2R_SCRIPTED_EXTERNAL_ARG1.with(|slot| slot.set(sector));
    __C2R_SCRIPTED_EXTERNAL_ARG2.with(|slot| slot.set(kv_size));
    __C2R_SCRIPTED_EXTERNAL_CALL_COUNT.with(|slot| {
        slot.set(slot.get().checked_add(1).expect("scripted external fixture call count overflow"));
    });
    __C2R_SCRIPTED_EXTERNAL_RETURN.with(|slot| slot.get())
}

pub fn fdb_alloc_compare_probe(db: u32, sector: u32, kv_size: usize, mut empty_kv_out: &mut [u32]) -> bool {
    let mut empty_kv: u32 = ((-1i32) as u32);
    let mut failed: bool = false;
    empty_kv = alloc_kv(db, sector, kv_size);
    if (empty_kv != ((-1i32) as u32)) {
        failed = true;
    }
    empty_kv_out[0usize] = empty_kv;
    return failed;
}

fn FDB_INFO(fmt: *const core::ffi::c_char, name: *const core::ffi::c_char) -> () {
    let _ = (fmt, name);
    // ignored non-observable void external callee per fixture replay_contract
}
pub fn db_init_ok(db: *mut core::ffi::c_void) -> bool {
    let _ = db;
    false
}
pub fn db_lock(db: *mut core::ffi::c_void) {
    let _ = db;
    unimplemented!("fdb_kv_del fixture model: db_lock is not exercised by uninitialized DB cases")
}
pub fn db_name(db: *mut core::ffi::c_void) -> *const core::ffi::c_char {
    let _ = db;
    b"unit-kv\0".as_ptr().cast::<core::ffi::c_char>()
}
pub fn db_unlock(db: *mut core::ffi::c_void) {
    let _ = db;
    unimplemented!("fdb_kv_del fixture model: db_unlock is not exercised by uninitialized DB cases")
}
pub fn del_kv(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, old_kv: *mut core::ffi::c_void, complete_del: bool) -> i32 {
    let _ = (db, key, old_kv, complete_del);
    unimplemented!("fdb_kv_del fixture model: del_kv is not exercised by uninitialized DB cases")
}

pub fn fdb_kv_del(db: *mut core::ffi::c_void, key: *const core::ffi::c_void) -> i32 {
    let mut result: i32 = 0i32;
    if db_init_ok(db) == false {
        FDB_INFO(b"Error: KV (%s) isn't initialize OK.\n\0".as_ptr().cast::<i8>(), db_name(db));
        return 7i32;
    }
    db_lock(db);
    result = del_kv(db, key, core::ptr::null_mut(), true);
    db_unlock(db);
    return result;
}

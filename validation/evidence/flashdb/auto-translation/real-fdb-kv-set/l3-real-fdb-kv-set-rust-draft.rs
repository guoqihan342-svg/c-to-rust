#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbBlob {
    pub buf: *mut core::ffi::c_void,
    pub size: usize,
}

pub fn fdb_kv_set(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: Option<&[i8]>) -> i32 {
    let mut blob: FdbBlob = FdbBlob { buf: core::ptr::null_mut(), size: 0usize };
    if value.is_some() {
        return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.unwrap().as_ptr() as *const core::ffi::c_void, value.unwrap().iter().position(|&byte| byte == 0).expect("C strlen precondition violated")));
    } else {
        return fdb_kv_del(db, key);
    }
}

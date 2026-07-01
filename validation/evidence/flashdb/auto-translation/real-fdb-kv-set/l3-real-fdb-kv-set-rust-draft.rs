#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbBlob {
    pub buf: *mut core::ffi::c_void,
    pub size: usize,
    pub saved: FdbBlobSaved,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbBlobSaved {
    pub meta_addr: u32,
    pub addr: u32,
    pub len: usize,
}

pub fn fdb_kv_set(db: *mut core::ffi::c_void, key: *const core::ffi::c_void, value: Option<&[i8]>) -> i32 {
    let mut blob: FdbBlob = FdbBlob { buf: core::ptr::null_mut(), size: 0usize, saved: FdbBlobSaved { meta_addr: 0u32, addr: 0u32, len: 0usize } };
    if value.is_some() {
        return fdb_kv_set_blob(db, key, fdb_blob_make(&mut blob, value.unwrap().as_ptr() as *const core::ffi::c_void, value.unwrap().iter().position(|&byte| byte == 0).expect("C strlen precondition violated")));
    } else {
        return fdb_kv_del(db, key);
    }
}

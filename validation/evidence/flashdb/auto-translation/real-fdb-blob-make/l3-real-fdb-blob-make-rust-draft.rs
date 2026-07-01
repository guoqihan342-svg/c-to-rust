#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbBlob {
    pub buf: *mut core::ffi::c_void,
    pub size: usize,
}

pub fn fdb_blob_make(mut blob: &mut FdbBlob, value_buf: *const core::ffi::c_void, buf_len: usize) -> &mut FdbBlob {
    blob.buf = (value_buf as *mut core::ffi::c_void);
    blob.size = buf_len;
    return blob;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbBlob {
    pub buf: *mut core::ffi::c_void,
    pub size: usize,
}

pub fn fdb_blob_make(
    blob: &mut FdbBlob,
    value_buf: *const core::ffi::c_void,
    buf_len: usize,
) -> &mut FdbBlob {
    blob.buf = value_buf.cast_mut();
    blob.size = buf_len;
    blob
}

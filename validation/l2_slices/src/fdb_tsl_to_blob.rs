#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct FdbTslAddr {
    pub index: u32,
    pub log: u32,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct FdbTsl {
    pub addr: FdbTslAddr,
    pub log_len: u32,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct FdbBlobSaved {
    pub meta_addr: u32,
    pub addr: u32,
    pub len: usize,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct FdbBlob {
    pub buf: *mut core::ffi::c_void,
    pub size: usize,
    pub saved: FdbBlobSaved,
}

pub fn fdb_tsl_to_blob<'a>(tsl: &FdbTsl, blob: &'a mut FdbBlob) -> &'a mut FdbBlob {
    blob.saved.addr = tsl.addr.log;
    blob.saved.meta_addr = tsl.addr.index;
    blob.saved.len = usize::try_from(tsl.log_len).expect("u32 log length must fit usize");
    blob
}

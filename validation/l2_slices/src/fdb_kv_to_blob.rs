#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKvAddr {
    pub start: u32,
    pub value: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbKv {
    pub addr: FdbKvAddr,
    pub value_len: usize,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbBlobSaved {
    pub meta_addr: u32,
    pub addr: u32,
    pub len: usize,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FdbBlob {
    pub saved: FdbBlobSaved,
}

pub fn fdb_kv_to_blob<'a>(kv: &FdbKv, blob: &'a mut FdbBlob) -> &'a mut FdbBlob {
    blob.saved.meta_addr = kv.addr.start;
    blob.saved.addr = kv.addr.value;
    blob.saved.len = kv.value_len;
    blob
}

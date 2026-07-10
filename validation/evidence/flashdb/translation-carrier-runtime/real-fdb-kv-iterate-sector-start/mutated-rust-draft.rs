#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Sector {
    pub addr: u32,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Kv {
    pub addr: Address,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Address {
    pub start: u32,
}

pub fn fdb_kv_iterate_sector_start_probe(sector: Sector, SECTOR_HDR_DATA_SIZE: u32, kv: &mut Kv) -> bool {
    kv.addr.start = sector.addr.wrapping_sub(SECTOR_HDR_DATA_SIZE);
    return true;
}

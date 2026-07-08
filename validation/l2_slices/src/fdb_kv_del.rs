#[derive(Clone, Debug, Eq, PartialEq)]
pub struct KvDbFixture {
    pub init_ok: bool,
    pub name: String,
}

pub fn fdb_kv_del(db: &KvDbFixture, _key: &str) -> i32 {
    if !db.init_ok {
        return 7;
    }
    unimplemented!("real-fdb-kv-del accepted fixture only covers uninitialized DB guard")
}

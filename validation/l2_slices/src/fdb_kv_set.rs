#[derive(Clone, Debug, Eq, PartialEq)]
pub struct KvDbFixture {
    pub init_ok: bool,
    pub name: String,
}

pub fn fdb_kv_set(db: &KvDbFixture, _key: &str, _value: Option<&str>) -> i32 {
    if !db.init_ok {
        return 7;
    }
    unimplemented!("real-fdb-kv-set accepted fixture only covers uninitialized DB guard")
}

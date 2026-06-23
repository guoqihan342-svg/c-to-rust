use flashdb_rust::{KvDb, MemoryFlash};

#[test]
fn kvdb_set_get_delete_iterate_compact_reopen() {
    let flash = MemoryFlash::new(4096);
    let mut db = KvDb::create(flash).unwrap();

    db.set("alpha", b"one").unwrap();
    db.set("beta", b"two").unwrap();
    db.set("alpha", b"updated").unwrap();

    assert_eq!(db.get("alpha").unwrap(), Some(b"updated".to_vec()));
    assert_eq!(db.get("missing").unwrap(), None);

    let entries = db.entries();
    assert_eq!(entries.len(), 2);
    assert_eq!(entries[0].key, "alpha");
    assert_eq!(entries[1].key, "beta");

    db.delete("beta").unwrap();
    assert_eq!(db.get("beta").unwrap(), None);
    db.compact().unwrap();

    let flash = db.into_flash();
    let reopened = KvDb::open(flash).unwrap();
    assert_eq!(reopened.get("alpha").unwrap(), Some(b"updated".to_vec()));
    assert_eq!(reopened.get("beta").unwrap(), None);
}

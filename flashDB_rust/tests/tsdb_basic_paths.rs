use flashdb_rust::{MemoryFlash, TsDb, TsStatus};

#[test]
fn tsdb_append_query_count_status_reopen() {
    let flash = MemoryFlash::new(4096);
    let mut db = TsDb::create(flash).unwrap();

    let first = db.append(10, b"a").unwrap();
    let second = db.append(20, b"b").unwrap();
    db.append(30, b"c").unwrap();
    db.set_status(second, TsStatus::UserStatus1).unwrap();

    let rows = db.query(5, 25);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].id, first);
    assert_eq!(rows[1].id, second);
    assert_eq!(db.count_by_status(0, 40, TsStatus::Written), 2);
    assert_eq!(db.count_by_status(0, 40, TsStatus::UserStatus1), 1);

    let reversed = db.query(30, 10);
    assert_eq!(reversed.len(), 3);
    assert_eq!(reversed[0].timestamp, 30);

    let flash = db.into_flash();
    let reopened = TsDb::open(flash).unwrap();
    assert_eq!(reopened.query(0, 40).len(), 3);
    assert_eq!(reopened.count_by_status(0, 40, TsStatus::UserStatus1), 1);
}

use flashdb_rust::{FileFlash, KvDb, TsDb};
use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

fn temp_path(name: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "flashdb_rust_{name}_{}_{}.img",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

#[test]
fn file_kvdb_reopen_preserves_committed_values() {
    let path = temp_path("kvdb");
    let mut db = KvDb::create(FileFlash::create(&path, 4096).unwrap()).unwrap();
    db.set("persist", b"value").unwrap();
    db.set("gone", b"old").unwrap();
    db.delete("gone").unwrap();
    drop(db);

    let reopened = KvDb::open(FileFlash::open(&path, 4096).unwrap()).unwrap();
    assert_eq!(reopened.get("persist").unwrap(), Some(b"value".to_vec()));
    assert_eq!(reopened.get("gone").unwrap(), None);
    let _ = fs::remove_file(path);
}

#[test]
fn file_tsdb_reopen_preserves_entries() {
    let path = temp_path("tsdb");
    let mut db = TsDb::create(FileFlash::create(&path, 4096).unwrap()).unwrap();
    db.append(100, b"temperature").unwrap();
    drop(db);

    let reopened = TsDb::open(FileFlash::open(&path, 4096).unwrap()).unwrap();
    let rows = reopened.query(100, 100);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].payload, b"temperature");
    let _ = fs::remove_file(path);
}

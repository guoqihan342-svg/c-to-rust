use flashdb_rust::format::{decode_record, encode_record, RecordKind};
use flashdb_rust::{Error, KvDb, MemoryFlash};

#[test]
fn kvdb_rejects_invalid_keys_and_capacity() {
    let mut db = KvDb::create(MemoryFlash::new(96)).unwrap();
    assert!(matches!(db.set("", b"value"), Err(Error::InvalidKey)));
    let long = "x".repeat(65);
    assert!(matches!(
        db.set(&long, b"value"),
        Err(Error::KeyTooLong { .. })
    ));
    assert!(matches!(
        db.set("large", &[1; 256]),
        Err(Error::CapacityExceeded { .. })
    ));
}

#[test]
fn decoder_rejects_truncated_and_crc_corrupt_records() {
    let encoded = encode_record(RecordKind::KvSet, 0, 0, b"k", b"v").unwrap();
    assert!(matches!(
        decode_record(&encoded[..encoded.len() - 1]),
        Err(Error::CorruptRecord(_))
    ));

    let mut corrupted = encoded;
    let last = corrupted.len() - 1;
    corrupted[last] ^= 0x80;
    assert!(matches!(
        decode_record(&corrupted),
        Err(Error::CrcMismatch { .. })
    ));
}

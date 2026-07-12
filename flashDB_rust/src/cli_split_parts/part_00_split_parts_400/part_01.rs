fn run_production_loop<KF, TF>(
    mut kv: KvDb<KF>,
    mut ts: TsDb<TF>,
    options: &Options,
    report: &mut Report,
    rng: &mut Lcg,
) -> Result<()>
where
    KF: FlashDevice,
    TF: FlashDevice,
{
    for i in 0..options.loops {
        let key = format!("key-{}", rng.next() % 97);
        let value = format!("value-{i}-{}", rng.next()).into_bytes();
        kv.set(&key, &value)?;
        assert_eq_or_error(kv.get(&key)?, Some(value.clone()), "kv get after set")?;
        if i % 5 == 0 {
            kv.delete(&key)?;
            assert_eq_or_error(kv.get(&key)?, None, "kv get after delete")?;
        }
        if i % 11 == 0 {
            kv.compact()?;
        }

        let ts_id = ts.append(i as i64, &value)?;
        if i % 7 == 0 {
            ts.set_status(ts_id, TsStatus::UserStatus1)?;
        }
        let from = (i as i64).saturating_sub(3);
        let rows = ts.query(from, i as i64);
        if rows.is_empty() {
            return Err(Error::CorruptRecord(
                "TS query unexpectedly empty".to_string(),
            ));
        }
        *report
            .scenario_counts
            .entry("production".to_string())
            .or_insert(0) += 1;
    }
    report.counters = report
        .counters
        .combined_with(kv.counters())
        .combined_with(ts.counters());
    report.bytes_processed += kv.bytes_used()? as u64 + ts.bytes_used()? as u64;
    report.image_hashes.push(kv.image_hash()?);
    report.image_hashes.push(ts.image_hash()?);
    Ok(())
}

fn run_abnormal(options: &Options, report: &mut Report) -> Result<()> {
    let mut kv = KvDb::create(MemoryFlash::new(options.size))?;
    assert!(matches!(kv.set("", b"value"), Err(Error::InvalidKey)));
    assert!(kv.get("missing")?.is_none());
    let long_key = "x".repeat(65);
    assert!(matches!(
        kv.set(&long_key, b"value"),
        Err(Error::KeyTooLong { .. })
    ));

    let mut tiny = KvDb::create(MemoryFlash::new(48))?;
    assert!(matches!(
        tiny.set("k", &[7; 96]),
        Err(Error::CapacityExceeded { .. })
    ));

    let encoded = encode_record(RecordKind::KvSet, 0, 0, b"k", b"v")?;
    let mut corrupted = encoded.clone();
    let last = corrupted.len() - 1;
    corrupted[last] ^= 1;
    assert!(matches!(
        decode_record(&corrupted),
        Err(Error::CrcMismatch { .. })
    ));
    assert!(matches!(
        decode_record(&encoded[..encoded.len() - 1]),
        Err(Error::CorruptRecord(_))
    ));

    report
        .scenario_counts
        .insert("abnormal".to_string(), options.loops);
    report.bytes_processed += encoded.len() as u64 + corrupted.len() as u64;
    Ok(())
}

fn run_reliability(options: &Options, report: &mut Report) -> Result<()> {
    let base = std::env::temp_dir().join(format!(
        "flashdb_rust_reliability_{}",
        unique_run_id(options.seed)
    ));
    fs::create_dir_all(&base)
        .map_err(|err| Error::Io(format!("create reliability dir {}: {err}", base.display())))?;
    let kv_path = base.join("kv.img");
    let ts_path = base.join("ts.img");
    let _ = fs::remove_file(&kv_path);
    let _ = fs::remove_file(&ts_path);

    let mut kv = KvDb::create(FileFlash::create(&kv_path, options.size).map_err(|err| {
        Error::Io(format!(
            "create reliability kv image {}: {err}",
            kv_path.display()
        ))
    })?)?;
    let mut ts = TsDb::create(FileFlash::create(&ts_path, options.size).map_err(|err| {
        Error::Io(format!(
            "create reliability ts image {}: {err}",
            ts_path.display()
        ))
    })?)?;
    for i in 0..options.loops {
        let key = format!("persist-{i}");
        kv.set(&key, format!("value-{i}").as_bytes())?;
        if i % 4 == 0 {
            kv.compact()?;
        }
        ts.append(i as i64, format!("payload-{i}").as_bytes())?;
        *report
            .scenario_counts
            .entry("reliability".to_string())
            .or_insert(0) += 1;
    }
    let kv_hash = kv.image_hash()?;
    let ts_hash = ts.image_hash()?;
    drop(kv);
    drop(ts);

    let kv_reopened = KvDb::open(FileFlash::open(&kv_path, options.size).map_err(|err| {
        Error::Io(format!(
            "open reliability kv image {}: {err}",
            kv_path.display()
        ))
    })?)?;
    let ts_reopened = TsDb::open(FileFlash::open(&ts_path, options.size).map_err(|err| {
        Error::Io(format!(
            "open reliability ts image {}: {err}",
            ts_path.display()
        ))
    })?)?;
    if options.loops > 0 {
        let last = options.loops - 1;
        let key = format!("persist-{last}");
        assert_eq_or_error(
            kv_reopened.get(&key)?,
            Some(format!("value-{last}").into_bytes()),
            "reopen kv",
        )?;
        if ts_reopened.query(last as i64, last as i64).is_empty() {
            return Err(Error::CorruptRecord("reopen ts query empty".to_string()));
        }
    }
    report.counters = report
        .counters
        .combined_with(kv_reopened.counters())
        .combined_with(ts_reopened.counters());
    report.image_hashes.push(kv_hash);
    report.image_hashes.push(ts_hash);
    drop(kv_reopened);
    drop(ts_reopened);
    let _ = fs::remove_dir_all(base);
    Ok(())
}

fn inspect_image(options: Options) -> Result<String> {
    let path = options
        .image
        .ok_or_else(|| Error::Cli("inspect-image requires --path".to_string()))?;
    let bytes = fs::read(&path)?;
    Ok(format!(
        "{{\"path\":\"{}\",\"bytes\":{},\"image_hash\":\"{}\"}}",
        escape_json(&path.display().to_string()),
        bytes.len(),
        image_hash(&bytes)
    ))
}

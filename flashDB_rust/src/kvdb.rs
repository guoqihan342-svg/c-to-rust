use crate::config::MAX_KEY_LEN;
use crate::flash::{FlashCounters, FlashDevice};
use crate::format::{encode_record, encoded_len, image_hash, scan_records_with_len, RecordKind};
use crate::types::{Error, Result};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KvEntry {
    pub key: String,
    pub value: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct KvDb<D: FlashDevice> {
    flash: D,
    entries: BTreeMap<String, Vec<u8>>,
    write_offset: usize,
}

impl<D: FlashDevice> KvDb<D> {
    pub fn create(mut flash: D) -> Result<Self> {
        flash.erase(0, flash.len())?;
        flash.flush()?;
        Ok(Self {
            flash,
            entries: BTreeMap::new(),
            write_offset: 0,
        })
    }

    pub fn open(mut flash: D) -> Result<Self> {
        let image = flash.image()?;
        let mut entries = BTreeMap::new();
        let (records, write_offset) = scan_records_with_len(&image)?;
        for record in records {
            match record.kind {
                RecordKind::KvSet => {
                    let key = String::from_utf8(record.key)
                        .map_err(|_| Error::CorruptRecord("key is not utf-8".to_string()))?;
                    entries.insert(key, record.payload);
                }
                RecordKind::KvDelete => {
                    let key = String::from_utf8(record.key)
                        .map_err(|_| Error::CorruptRecord("key is not utf-8".to_string()))?;
                    entries.remove(&key);
                }
                RecordKind::TsAppend => {}
            }
        }
        Ok(Self {
            flash,
            entries,
            write_offset,
        })
    }

    pub fn into_flash(self) -> D {
        self.flash
    }

    pub fn set(&mut self, key: &str, value: &[u8]) -> Result<()> {
        validate_key(key)?;
        let record = encode_record(RecordKind::KvSet, 0, 0, key.as_bytes(), value)?;
        self.append_record(record)?;
        self.entries.insert(key.to_string(), value.to_vec());
        Ok(())
    }

    pub fn get(&self, key: &str) -> Result<Option<Vec<u8>>> {
        validate_key(key)?;
        Ok(self.entries.get(key).cloned())
    }

    pub fn delete(&mut self, key: &str) -> Result<()> {
        validate_key(key)?;
        let record = encode_record(RecordKind::KvDelete, 0, 0, key.as_bytes(), &[])?;
        self.append_record(record)?;
        self.entries.remove(key);
        Ok(())
    }

    pub fn entries(&self) -> Vec<KvEntry> {
        self.entries
            .iter()
            .map(|(key, value)| KvEntry {
                key: key.clone(),
                value: value.clone(),
            })
            .collect()
    }

    pub fn compact(&mut self) -> Result<()> {
        self.persist_snapshot()
    }

    pub fn counters(&self) -> FlashCounters {
        self.flash.counters()
    }

    pub fn image_hash(&mut self) -> Result<String> {
        let image = self.flash.image()?;
        Ok(image_hash(&image))
    }

    pub fn bytes_used(&self) -> Result<usize> {
        Ok(self.write_offset)
    }

    fn persist_snapshot(&mut self) -> Result<()> {
        let records = self.encoded_records()?;
        let needed = encoded_len(&records);
        let capacity = self.flash.len();
        if needed > capacity {
            return Err(Error::CapacityExceeded { needed, capacity });
        }
        self.flash.erase(0, self.write_offset.max(needed))?;
        let mut offset = 0;
        for record in records {
            self.flash.write(offset, &record)?;
            offset += record.len();
        }
        self.write_offset = offset;
        self.flash.flush()
    }

    fn append_record(&mut self, record: Vec<u8>) -> Result<()> {
        let capacity = self.flash.len();
        if record.len() > capacity {
            return Err(Error::CapacityExceeded {
                needed: record.len(),
                capacity,
            });
        }
        if self.write_offset + record.len() > capacity {
            self.persist_snapshot()?;
        }
        if self.write_offset + record.len() > capacity {
            return Err(Error::CapacityExceeded {
                needed: self.write_offset + record.len(),
                capacity,
            });
        }
        self.flash.write(self.write_offset, &record)?;
        self.write_offset += record.len();
        self.flash.flush()
    }

    fn encoded_records(&self) -> Result<Vec<Vec<u8>>> {
        self.entries
            .iter()
            .map(|(key, value)| encode_record(RecordKind::KvSet, 0, 0, key.as_bytes(), value))
            .collect()
    }
}

fn validate_key(key: &str) -> Result<()> {
    if key.is_empty() {
        return Err(Error::InvalidKey);
    }
    if key.len() > MAX_KEY_LEN {
        return Err(Error::KeyTooLong {
            len: key.len(),
            max: MAX_KEY_LEN,
        });
    }
    Ok(())
}

use crate::config::MAX_TSDB_PAYLOAD_LEN;
use crate::flash::{FlashCounters, FlashDevice};
use crate::format::{encode_record, encoded_len, image_hash, scan_records_with_len, RecordKind};
use crate::types::{Error, Result, TsStatus};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TsEntry {
    pub id: u64,
    pub timestamp: i64,
    pub status: TsStatus,
    pub payload: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct TsDb<D: FlashDevice> {
    flash: D,
    entries: Vec<TsEntry>,
    next_id: u64,
    write_offset: usize,
}

impl<D: FlashDevice> TsDb<D> {
    pub fn create(mut flash: D) -> Result<Self> {
        flash.erase(0, flash.len())?;
        flash.flush()?;
        Ok(Self {
            flash,
            entries: Vec::new(),
            next_id: 1,
            write_offset: 0,
        })
    }

    pub fn open(mut flash: D) -> Result<Self> {
        let image = flash.image()?;
        let mut entries = BTreeMap::new();
        let mut next_id = 1;
        let (records, write_offset) = scan_records_with_len(&image)?;
        for record in records {
            if record.kind != RecordKind::TsAppend {
                continue;
            }
            if record.key.len() != 8 {
                return Err(Error::CorruptRecord(
                    "TS id key must be 8 bytes".to_string(),
                ));
            }
            let id = u64::from_le_bytes(record.key[..8].try_into().expect("length checked"));
            next_id = next_id.max(id + 1);
            entries.insert(
                id,
                TsEntry {
                    id,
                    timestamp: record.timestamp,
                    status: TsStatus::from_u8(record.status)?,
                    payload: record.payload,
                },
            );
        }
        Ok(Self {
            flash,
            entries: entries.into_values().collect(),
            next_id,
            write_offset,
        })
    }

    pub fn into_flash(self) -> D {
        self.flash
    }

    pub fn append(&mut self, timestamp: i64, payload: &[u8]) -> Result<u64> {
        if payload.len() > MAX_TSDB_PAYLOAD_LEN {
            return Err(Error::WriteError(format!(
                "TSDB payload length {} exceeds max {}",
                payload.len(),
                MAX_TSDB_PAYLOAD_LEN
            )));
        }
        let id = self.next_id;
        let entry = TsEntry {
            id,
            timestamp,
            status: TsStatus::Written,
            payload: payload.to_vec(),
        };
        let record = Self::encode_entry(&entry)?;
        self.append_record(record)?;
        self.entries.push(entry);
        self.next_id += 1;
        Ok(id)
    }

    pub fn query(&self, from: i64, to: i64) -> Vec<TsEntry> {
        let mut out: Vec<TsEntry> = if from <= to {
            self.entries
                .iter()
                .filter(|entry| entry.timestamp >= from && entry.timestamp <= to)
                .cloned()
                .collect()
        } else {
            self.entries
                .iter()
                .filter(|entry| entry.timestamp <= from && entry.timestamp >= to)
                .cloned()
                .collect()
        };
        if from > to {
            out.reverse();
        }
        out
    }

    pub fn count_by_status(&self, from: i64, to: i64, status: TsStatus) -> usize {
        self.query(from, to)
            .into_iter()
            .filter(|entry| entry.status == status)
            .count()
    }

    pub fn set_status(&mut self, id: u64, status: TsStatus) -> Result<()> {
        let index = self
            .entries
            .iter()
            .position(|entry| entry.id == id)
            .ok_or_else(|| Error::InvalidRange(format!("unknown TS entry id {id}")))?;
        let mut updated = self.entries[index].clone();
        updated.status = status;
        let record = Self::encode_entry(&updated)?;
        self.append_record(record)?;
        self.entries[index] = updated;
        Ok(())
    }

    pub fn entries(&self) -> Vec<TsEntry> {
        self.entries.clone()
    }

    pub fn counters(&self) -> FlashCounters {
        self.flash.counters()
    }

    pub fn image_hash(&mut self) -> Result<String> {
        let image = self.image()?;
        Ok(image_hash(&image))
    }

    pub fn image(&mut self) -> Result<Vec<u8>> {
        self.flash.image()
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
        self.entries.iter().map(Self::encode_entry).collect()
    }

    fn encode_entry(entry: &TsEntry) -> Result<Vec<u8>> {
        encode_record(
            RecordKind::TsAppend,
            entry.status.as_u8(),
            entry.timestamp,
            &entry.id.to_le_bytes(),
            &entry.payload,
        )
    }
}

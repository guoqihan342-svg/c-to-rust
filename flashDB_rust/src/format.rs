use crate::config::{ERASED_VALUE, MAX_KEY_LEN};
use crate::types::{Error, Result};

const MAGIC: [u8; 4] = *b"FDBR";
const HEADER_LEN: usize = 28;

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum RecordKind {
    KvSet = 1,
    KvDelete = 2,
    TsAppend = 3,
}

impl RecordKind {
    fn from_u8(value: u8) -> Result<Self> {
        match value {
            1 => Ok(RecordKind::KvSet),
            2 => Ok(RecordKind::KvDelete),
            3 => Ok(RecordKind::TsAppend),
            other => Err(Error::CorruptRecord(format!("unknown record kind {other}"))),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Record {
    pub kind: RecordKind,
    pub status: u8,
    pub timestamp: i64,
    pub key: Vec<u8>,
    pub payload: Vec<u8>,
}

pub fn crc32_update(crc: u32, bytes: &[u8]) -> u32 {
    let mut crc = crc ^ 0xFFFF_FFFF;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = 0u32.wrapping_sub(crc & 1);
            crc = (crc >> 1) ^ (0xEDB8_8320 & mask);
        }
    }
    crc ^ 0xFFFF_FFFF
}

pub fn align_down(value: usize, granularity: usize) -> Result<usize> {
    if granularity == 0 {
        return Err(Error::InvalidRange(
            "granularity must be greater than zero".to_string(),
        ));
    }
    Ok(value / granularity * granularity)
}

pub fn align_up(value: usize, granularity: usize) -> Result<usize> {
    if granularity == 0 {
        return Err(Error::InvalidRange(
            "granularity must be greater than zero".to_string(),
        ));
    }
    let rem = value % granularity;
    if rem == 0 {
        Ok(value)
    } else {
        value
            .checked_add(granularity - rem)
            .ok_or_else(|| Error::InvalidRange("alignment overflow".to_string()))
    }
}

pub fn encode_record(
    kind: RecordKind,
    status: u8,
    timestamp: i64,
    key: &[u8],
    payload: &[u8],
) -> Result<Vec<u8>> {
    if key.len() > MAX_KEY_LEN {
        return Err(Error::KeyTooLong {
            len: key.len(),
            max: MAX_KEY_LEN,
        });
    }
    let key_len: u32 = key
        .len()
        .try_into()
        .map_err(|_| Error::InvalidRange("key too large".to_string()))?;
    let payload_len: u32 = payload
        .len()
        .try_into()
        .map_err(|_| Error::InvalidRange("payload too large".to_string()))?;

    let mut prefix = Vec::with_capacity(HEADER_LEN - 4);
    prefix.extend_from_slice(&MAGIC);
    prefix.push(kind as u8);
    prefix.push(status);
    prefix.extend_from_slice(&0u16.to_le_bytes());
    prefix.extend_from_slice(&timestamp.to_le_bytes());
    prefix.extend_from_slice(&key_len.to_le_bytes());
    prefix.extend_from_slice(&payload_len.to_le_bytes());

    let mut crc = crc32_update(0, &prefix);
    crc = crc32_update(crc, key);
    crc = crc32_update(crc, payload);

    let mut out = Vec::with_capacity(HEADER_LEN + key.len() + payload.len());
    out.extend_from_slice(&prefix);
    out.extend_from_slice(&crc.to_le_bytes());
    out.extend_from_slice(key);
    out.extend_from_slice(payload);
    Ok(out)
}

pub fn decode_record(input: &[u8]) -> Result<Option<(Record, usize)>> {
    if input.is_empty() || input.iter().all(|b| *b == ERASED_VALUE) {
        return Ok(None);
    }
    if input.len() < HEADER_LEN {
        return Err(Error::CorruptRecord("truncated header".to_string()));
    }
    if input[0..4] != MAGIC {
        return Err(Error::CorruptRecord("invalid magic".to_string()));
    }

    let kind = RecordKind::from_u8(input[4])?;
    let status = input[5];
    let timestamp = i64::from_le_bytes(input[8..16].try_into().expect("slice length checked"));
    let key_len =
        u32::from_le_bytes(input[16..20].try_into().expect("slice length checked")) as usize;
    let payload_len =
        u32::from_le_bytes(input[20..24].try_into().expect("slice length checked")) as usize;
    let expected_crc = u32::from_le_bytes(input[24..28].try_into().expect("slice length checked"));

    if key_len > MAX_KEY_LEN {
        return Err(Error::KeyTooLong {
            len: key_len,
            max: MAX_KEY_LEN,
        });
    }

    let total = HEADER_LEN
        .checked_add(key_len)
        .and_then(|v| v.checked_add(payload_len))
        .ok_or_else(|| Error::CorruptRecord("record length overflow".to_string()))?;
    if input.len() < total {
        return Err(Error::CorruptRecord("truncated record".to_string()));
    }

    let key_start = HEADER_LEN;
    let payload_start = HEADER_LEN + key_len;
    let key = input[key_start..payload_start].to_vec();
    let payload = input[payload_start..total].to_vec();

    let mut crc = crc32_update(0, &input[..24]);
    crc = crc32_update(crc, &key);
    crc = crc32_update(crc, &payload);
    if crc != expected_crc {
        return Err(Error::CrcMismatch {
            expected: expected_crc,
            actual: crc,
        });
    }

    Ok(Some((
        Record {
            kind,
            status,
            timestamp,
            key,
            payload,
        },
        total,
    )))
}

pub fn scan_records(image: &[u8]) -> Result<Vec<Record>> {
    Ok(scan_records_with_len(image)?.0)
}

pub fn scan_records_with_len(image: &[u8]) -> Result<(Vec<Record>, usize)> {
    let mut out = Vec::new();
    let mut offset = 0;
    while offset < image.len() {
        if image[offset..].iter().all(|b| *b == ERASED_VALUE) {
            break;
        }
        match decode_record(&image[offset..])? {
            Some((record, consumed)) => {
                out.push(record);
                offset += consumed;
            }
            None => break,
        }
    }
    Ok((out, offset))
}

pub fn image_hash(bytes: &[u8]) -> String {
    format!("{:08x}", crc32_update(0, bytes))
}

pub fn encoded_len(records: &[Vec<u8>]) -> usize {
    records.iter().map(Vec::len).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crc32_matches_standard_vector() {
        assert_eq!(crc32_update(0, b"123456789"), 0xcbf4_3926);
        let crc = crc32_update(crc32_update(0, b"1234"), b"56789");
        assert_eq!(crc, 0xcbf4_3926);
    }

    #[test]
    fn align_helpers_work() {
        assert_eq!(align_down(17, 8).unwrap(), 16);
        assert_eq!(align_up(17, 8).unwrap(), 24);
        assert_eq!(align_up(16, 8).unwrap(), 16);
    }

    #[test]
    fn record_round_trips_and_rejects_corruption() {
        let encoded = encode_record(RecordKind::KvSet, 0, 7, b"name", b"value").unwrap();
        let (decoded, consumed) = decode_record(&encoded).unwrap().unwrap();
        assert_eq!(consumed, encoded.len());
        assert_eq!(decoded.kind, RecordKind::KvSet);
        assert_eq!(decoded.timestamp, 7);
        assert_eq!(decoded.key, b"name");
        assert_eq!(decoded.payload, b"value");

        let mut corrupted = encoded;
        let last = corrupted.len() - 1;
        corrupted[last] ^= 0x01;
        assert!(matches!(
            decode_record(&corrupted),
            Err(Error::CrcMismatch { .. })
        ));
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DecodedVarint {
    pub value: u64,
    pub bytes_used: usize,
}

pub fn put_varint(value: u64) -> Vec<u8> {
    if value <= 0x7f {
        return vec![value as u8];
    }
    if value <= 0x3fff {
        return vec![(((value >> 7) & 0x7f) as u8) | 0x80, (value & 0x7f) as u8];
    }
    if value & (((0xff_u64) << 32) << 24) != 0 {
        let mut out = vec![0_u8; 9];
        let mut v = value;
        out[8] = v as u8;
        v >>= 8;
        for index in (0..8).rev() {
            out[index] = ((v & 0x7f) as u8) | 0x80;
            v >>= 7;
        }
        return out;
    }

    let mut v = value;
    let mut tmp = Vec::with_capacity(9);
    loop {
        tmp.push(((v & 0x7f) as u8) | 0x80);
        v >>= 7;
        if v == 0 {
            break;
        }
    }
    tmp[0] &= 0x7f;
    tmp.into_iter().rev().collect()
}

pub fn get_varint(bytes: &[u8]) -> Option<DecodedVarint> {
    let mut value = 0_u64;
    for (index, byte) in bytes.iter().copied().enumerate().take(9) {
        if index == 8 {
            value = (value << 8) | u64::from(byte);
            return Some(DecodedVarint {
                value,
                bytes_used: 9,
            });
        }

        value = (value << 7) | u64::from(byte & 0x7f);
        if byte & 0x80 == 0 {
            return Some(DecodedVarint {
                value,
                bytes_used: index + 1,
            });
        }
    }
    None
}

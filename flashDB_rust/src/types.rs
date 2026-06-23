use std::fmt;

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    InvalidKey,
    KeyTooLong {
        len: usize,
        max: usize,
    },
    InvalidRange(String),
    OutOfBounds {
        addr: usize,
        size: usize,
        len: usize,
    },
    CapacityExceeded {
        needed: usize,
        capacity: usize,
    },
    CrcMismatch {
        expected: u32,
        actual: u32,
    },
    CorruptRecord(String),
    Io(String),
    Parse(String),
    Cli(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::InvalidKey => write!(f, "key must not be empty"),
            Error::KeyTooLong { len, max } => write!(f, "key length {len} exceeds max {max}"),
            Error::InvalidRange(msg) => write!(f, "invalid range: {msg}"),
            Error::OutOfBounds { addr, size, len } => {
                write!(f, "out of bounds: addr={addr}, size={size}, len={len}")
            }
            Error::CapacityExceeded { needed, capacity } => {
                write!(f, "capacity exceeded: needed={needed}, capacity={capacity}")
            }
            Error::CrcMismatch { expected, actual } => {
                write!(
                    f,
                    "crc mismatch: expected={expected:#010x}, actual={actual:#010x}"
                )
            }
            Error::CorruptRecord(msg) => write!(f, "corrupt record: {msg}"),
            Error::Io(msg) => write!(f, "io error: {msg}"),
            Error::Parse(msg) => write!(f, "parse error: {msg}"),
            Error::Cli(msg) => write!(f, "cli error: {msg}"),
        }
    }
}

impl Error {
    pub fn code(&self) -> &'static str {
        match self {
            Error::InvalidKey => "INVALID_KEY",
            Error::KeyTooLong { .. } => "KEY_TOO_LONG",
            Error::InvalidRange(_) => "INVALID_RANGE",
            Error::OutOfBounds { .. } => "OUT_OF_BOUNDS",
            Error::CapacityExceeded { .. } => "CAPACITY_EXCEEDED",
            Error::CrcMismatch { .. } => "CRC_MISMATCH",
            Error::CorruptRecord(_) => "CORRUPT_RECORD",
            Error::Io(_) => "IO",
            Error::Parse(_) => "PARSE",
            Error::Cli(_) => "CLI",
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(value: std::io::Error) -> Self {
        Error::Io(value.to_string())
    }
}

#[derive(Debug, Copy, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct FlashAddr(pub usize);

#[derive(Debug, Copy, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct SectorOffset(pub usize);

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum TsStatus {
    Written,
    UserStatus1,
    Deleted,
    UserStatus2,
}

impl TsStatus {
    pub fn as_u8(self) -> u8 {
        match self {
            TsStatus::Written => 0,
            TsStatus::UserStatus1 => 1,
            TsStatus::Deleted => 2,
            TsStatus::UserStatus2 => 3,
        }
    }

    pub fn from_u8(value: u8) -> Result<Self> {
        match value {
            0 => Ok(TsStatus::Written),
            1 => Ok(TsStatus::UserStatus1),
            2 => Ok(TsStatus::Deleted),
            3 => Ok(TsStatus::UserStatus2),
            other => Err(Error::CorruptRecord(format!("unknown TS status {other}"))),
        }
    }
}

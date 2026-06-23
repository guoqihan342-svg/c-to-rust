use crate::types::{Error, Result};

pub const ERASED_VALUE: u8 = 0xFF;
pub const DEFAULT_FLASH_SIZE: usize = 4 * 1024 * 1024;
pub const DEFAULT_SECTOR_SIZE: usize = 4 * 1024;
pub const DEFAULT_WRITE_GRAN: usize = 1;
pub const MAX_KEY_LEN: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DbConfig {
    pub flash_size: usize,
    pub sector_size: usize,
    pub write_gran: usize,
    pub max_key_len: usize,
}

impl Default for DbConfig {
    fn default() -> Self {
        Self {
            flash_size: DEFAULT_FLASH_SIZE,
            sector_size: DEFAULT_SECTOR_SIZE,
            write_gran: DEFAULT_WRITE_GRAN,
            max_key_len: MAX_KEY_LEN,
        }
    }
}

impl DbConfig {
    pub fn validate(&self) -> Result<()> {
        if self.flash_size == 0 || self.sector_size == 0 || self.write_gran == 0 {
            return Err(Error::InvalidRange(
                "sizes must be greater than zero".to_string(),
            ));
        }
        if self.flash_size % self.sector_size != 0 {
            return Err(Error::InvalidRange(
                "flash size must align to sector size".to_string(),
            ));
        }
        if self.flash_size / self.sector_size < 2 {
            return Err(Error::InvalidRange(
                "database must contain at least two sectors".to_string(),
            ));
        }
        Ok(())
    }
}

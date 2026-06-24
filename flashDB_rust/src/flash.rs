use crate::config::ERASED_VALUE;
use crate::types::{Error, Result};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

#[derive(Debug, Copy, Clone, Default, PartialEq, Eq)]
pub struct FlashCounters {
    pub read_ops: u64,
    pub write_ops: u64,
    pub erase_ops: u64,
    pub flush_ops: u64,
    pub bytes_read: u64,
    pub bytes_written: u64,
    pub bytes_erased: u64,
}

impl FlashCounters {
    pub fn combined_with(self, other: FlashCounters) -> FlashCounters {
        FlashCounters {
            read_ops: self.read_ops + other.read_ops,
            write_ops: self.write_ops + other.write_ops,
            erase_ops: self.erase_ops + other.erase_ops,
            flush_ops: self.flush_ops + other.flush_ops,
            bytes_read: self.bytes_read + other.bytes_read,
            bytes_written: self.bytes_written + other.bytes_written,
            bytes_erased: self.bytes_erased + other.bytes_erased,
        }
    }
}

pub trait FlashDevice {
    fn len(&self) -> usize;
    fn read(&mut self, addr: usize, buf: &mut [u8]) -> Result<()>;
    fn write(&mut self, addr: usize, data: &[u8]) -> Result<()>;
    fn erase(&mut self, addr: usize, size: usize) -> Result<()>;
    fn flush(&mut self) -> Result<()>;
    fn counters(&self) -> FlashCounters;

    fn image(&mut self) -> Result<Vec<u8>> {
        let mut out = vec![0; self.len()];
        self.read(0, &mut out)?;
        Ok(out)
    }

    fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

fn check_bounds(len: usize, addr: usize, size: usize) -> Result<()> {
    let end = addr
        .checked_add(size)
        .ok_or_else(|| Error::InvalidRange("address overflow".to_string()))?;
    if end > len {
        return Err(Error::OutOfBounds { addr, size, len });
    }
    Ok(())
}

#[derive(Debug, Clone)]
pub struct MemoryFlash {
    storage: Vec<u8>,
    counters: FlashCounters,
}

impl MemoryFlash {
    pub fn new(size: usize) -> Self {
        Self {
            storage: vec![ERASED_VALUE; size],
            counters: FlashCounters::default(),
        }
    }

    pub fn from_bytes(bytes: Vec<u8>) -> Self {
        Self {
            storage: bytes,
            counters: FlashCounters::default(),
        }
    }
}

impl FlashDevice for MemoryFlash {
    fn len(&self) -> usize {
        self.storage.len()
    }

    fn read(&mut self, addr: usize, buf: &mut [u8]) -> Result<()> {
        check_bounds(self.storage.len(), addr, buf.len())?;
        buf.copy_from_slice(&self.storage[addr..addr + buf.len()]);
        self.counters.read_ops += 1;
        self.counters.bytes_read += buf.len() as u64;
        Ok(())
    }

    fn write(&mut self, addr: usize, data: &[u8]) -> Result<()> {
        check_bounds(self.storage.len(), addr, data.len())?;
        self.storage[addr..addr + data.len()].copy_from_slice(data);
        self.counters.write_ops += 1;
        self.counters.bytes_written += data.len() as u64;
        Ok(())
    }

    fn erase(&mut self, addr: usize, size: usize) -> Result<()> {
        check_bounds(self.storage.len(), addr, size)?;
        self.storage[addr..addr + size].fill(ERASED_VALUE);
        self.counters.erase_ops += 1;
        self.counters.bytes_erased += size as u64;
        Ok(())
    }

    fn flush(&mut self) -> Result<()> {
        self.counters.flush_ops += 1;
        Ok(())
    }

    fn counters(&self) -> FlashCounters {
        self.counters
    }
}

#[derive(Debug)]
pub struct FileFlash {
    path: PathBuf,
    file: File,
    len: usize,
    counters: FlashCounters,
    sync_on_flush: bool,
}

impl FileFlash {
    pub fn create(path: impl AsRef<Path>, len: usize) -> Result<Self> {
        let path = path.as_ref().to_path_buf();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(&path)
            .map_err(|err| Error::Io(format!("create {}: {err}", path.display())))?;
        write_erased(&mut file, len)
            .map_err(|err| Error::Io(format!("initialize {}: {err}", path.display())))?;
        file.sync_all()
            .map_err(|err| Error::Io(format!("sync {} after create: {err}", path.display())))?;
        Ok(Self {
            path,
            file,
            len,
            counters: FlashCounters::default(),
            sync_on_flush: sync_on_flush(),
        })
    }

    pub fn open(path: impl AsRef<Path>, len: usize) -> Result<Self> {
        let path = path.as_ref().to_path_buf();
        if !path.exists() {
            return Self::create(path, len);
        }
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .map_err(|err| Error::Io(format!("open {}: {err}", path.display())))?;
        let current = file
            .metadata()
            .map_err(|err| Error::Io(format!("metadata {}: {err}", path.display())))?
            .len() as usize;
        if current < len {
            file.seek(SeekFrom::End(0))
                .map_err(|err| Error::Io(format!("seek end {}: {err}", path.display())))?;
            write_erased(&mut file, len - current)
                .map_err(|err| Error::Io(format!("extend {}: {err}", path.display())))?;
            file.sync_all()
                .map_err(|err| Error::Io(format!("sync {} after extend: {err}", path.display())))?;
        }
        Ok(Self {
            path,
            file,
            len,
            counters: FlashCounters::default(),
            sync_on_flush: sync_on_flush(),
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }
}

impl FlashDevice for FileFlash {
    fn len(&self) -> usize {
        self.len
    }

    fn read(&mut self, addr: usize, buf: &mut [u8]) -> Result<()> {
        check_bounds(self.len, addr, buf.len())?;
        self.file
            .seek(SeekFrom::Start(addr as u64))
            .map_err(|err| {
                Error::Io(format!(
                    "seek read {} at {addr}: {err}",
                    self.path.display()
                ))
            })?;
        self.file
            .read_exact(buf)
            .map_err(|err| Error::Io(format!("read {} at {addr}: {err}", self.path.display())))?;
        self.counters.read_ops += 1;
        self.counters.bytes_read += buf.len() as u64;
        Ok(())
    }

    fn write(&mut self, addr: usize, data: &[u8]) -> Result<()> {
        check_bounds(self.len, addr, data.len())?;
        self.file
            .seek(SeekFrom::Start(addr as u64))
            .map_err(|err| {
                Error::Io(format!(
                    "seek write {} at {addr}: {err}",
                    self.path.display()
                ))
            })?;
        self.file.write_all(data).map_err(|err| {
            Error::Io(format!(
                "write {} at {} size {}: {err}",
                self.path.display(),
                addr,
                data.len()
            ))
        })?;
        self.counters.write_ops += 1;
        self.counters.bytes_written += data.len() as u64;
        Ok(())
    }

    fn erase(&mut self, addr: usize, size: usize) -> Result<()> {
        check_bounds(self.len, addr, size)?;
        self.file
            .seek(SeekFrom::Start(addr as u64))
            .map_err(|err| {
                Error::Io(format!(
                    "seek erase {} at {addr}: {err}",
                    self.path.display()
                ))
            })?;
        write_erased(&mut self.file, size).map_err(|err| {
            Error::Io(format!(
                "erase {} at {} size {}: {err}",
                self.path.display(),
                addr,
                size
            ))
        })?;
        self.counters.erase_ops += 1;
        self.counters.bytes_erased += size as u64;
        Ok(())
    }

    fn flush(&mut self) -> Result<()> {
        if self.sync_on_flush {
            self.file
                .sync_all()
                .map_err(|err| Error::Io(format!("sync {}: {err}", self.path.display())))?;
        }
        self.counters.flush_ops += 1;
        Ok(())
    }

    fn counters(&self) -> FlashCounters {
        self.counters
    }
}

fn sync_on_flush() -> bool {
    std::env::var_os("FLASHDB_RUST_SYNC_ON_FLUSH").is_some()
}

fn write_erased(file: &mut File, len: usize) -> Result<()> {
    const CHUNK: usize = 4096;
    let chunk = [ERASED_VALUE; CHUNK];
    let mut remaining = len;
    while remaining > 0 {
        let n = remaining.min(CHUNK);
        file.write_all(&chunk[..n])?;
        remaining -= n;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn memory_flash_read_write_erase_and_bounds() {
        let mut flash = MemoryFlash::new(16);
        flash.write(2, &[1, 2, 3]).unwrap();
        let mut buf = [0; 3];
        flash.read(2, &mut buf).unwrap();
        assert_eq!(&buf, &[1, 2, 3]);
        flash.erase(2, 3).unwrap();
        flash.read(2, &mut buf).unwrap();
        assert_eq!(&buf, &[ERASED_VALUE; 3]);
        assert!(matches!(
            flash.write(15, &[1, 2]),
            Err(Error::OutOfBounds { .. })
        ));
    }

    #[test]
    fn file_flash_reopens() {
        let path = std::env::temp_dir().join(format!(
            "flashdb_rust_file_flash_{}.img",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let mut flash = FileFlash::create(&path, 32).unwrap();
        flash.write(4, &[7, 8, 9]).unwrap();
        flash.flush().unwrap();

        let mut reopened = FileFlash::open(&path, 32).unwrap();
        let mut buf = [0; 3];
        reopened.read(4, &mut buf).unwrap();
        assert_eq!(&buf, &[7, 8, 9]);
        let _ = std::fs::remove_file(path);
    }
}

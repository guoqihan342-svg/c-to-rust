// c2rust generated source: validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c2rust-baseline-generated/build.rs
#[cfg(all(unix, not(target_os = "macos")))]
fn main() {
    // add unix dependencies below
    // println!("cargo:rustc-flags=-l readline");
}

#[cfg(target_os = "macos")]
fn main() {
    // add macos dependencies below
    // println!("cargo:rustc-flags=-l edit");
}

// c2rust generated source: validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c2rust-baseline-generated/lib.rs
#![allow(clippy::missing_safety_doc)]
#![allow(dead_code)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(non_upper_case_globals)]
#![allow(unused_assignments)]
#![allow(unused_mut)]
#![feature(label_break_value)]
#![feature(raw_ref_op)]

pub mod src {
    pub mod fdb_utils;
} // mod src

// c2rust generated source: validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c2rust-baseline-generated/src/fdb_utils.rs
extern "C" {
    fn memcpy(
        __dest: *mut ::core::ffi::c_void,
        __src: *const ::core::ffi::c_void,
        __n: size_t,
    ) -> *mut ::core::ffi::c_void;
    fn memset(
        __s: *mut ::core::ffi::c_void,
        __c: ::core::ffi::c_int,
        __n: size_t,
    ) -> *mut ::core::ffi::c_void;
    fn __assert_fail(
        __assertion: *const ::core::ffi::c_char,
        __file: *const ::core::ffi::c_char,
        __line: ::core::ffi::c_uint,
        __function: *const ::core::ffi::c_char,
    ) -> !;
    fn _fdb_file_read(
        db: fdb_db_t,
        addr: uint32_t,
        buf: *mut ::core::ffi::c_void,
        size: size_t,
    ) -> fdb_err_t;
    fn _fdb_file_write(
        db: fdb_db_t,
        addr: uint32_t,
        buf: *const ::core::ffi::c_void,
        size: size_t,
        sync: bool,
    ) -> fdb_err_t;
    fn _fdb_file_erase(db: fdb_db_t, addr: uint32_t, size: size_t) -> fdb_err_t;
}
pub type size_t = usize;
pub type uint8_t = u8;
pub type uint32_t = u32;
pub type fdb_err_t = ::core::ffi::c_uint;
pub const FDB_INIT_FAILED: fdb_err_t = 7;
pub const FDB_SAVED_FULL: fdb_err_t = 6;
pub const FDB_KV_NAME_EXIST: fdb_err_t = 5;
pub const FDB_KV_NAME_ERR: fdb_err_t = 4;
pub const FDB_WRITE_ERR: fdb_err_t = 3;
pub const FDB_READ_ERR: fdb_err_t = 2;
pub const FDB_ERASE_ERR: fdb_err_t = 1;
pub const FDB_NO_ERR: fdb_err_t = 0;
pub type fdb_db_type = ::core::ffi::c_uint;
pub const FDB_DB_TYPE_TS: fdb_db_type = 1;
pub const FDB_DB_TYPE_KV: fdb_db_type = 0;
#[derive(Copy, Clone)]
#[repr(C)]
pub struct fdb_db {
    pub name: *const ::core::ffi::c_char,
    pub type_0: fdb_db_type,
    pub storage: C2Rust_Unnamed,
    pub sec_size: uint32_t,
    pub max_size: uint32_t,
    pub oldest_addr: uint32_t,
    pub init_ok: bool,
    pub file_mode: bool,
    pub not_formatable: bool,
    pub cur_file_sec: [uint32_t; 2],
    pub cur_file: [::core::ffi::c_int; 2],
    pub cur_sec: uint32_t,
    pub lock: Option<unsafe extern "C" fn(fdb_db_t) -> ()>,
    pub unlock: Option<unsafe extern "C" fn(fdb_db_t) -> ()>,
    pub user_data: *mut ::core::ffi::c_void,
}
pub type fdb_db_t = *mut fdb_db;
#[derive(Copy, Clone)]
#[repr(C)]
pub union C2Rust_Unnamed {
    pub dir: *const ::core::ffi::c_char,
}
#[derive(Copy, Clone)]
#[repr(C)]
pub struct fdb_blob {
    pub buf: *mut ::core::ffi::c_void,
    pub size: size_t,
    pub saved: C2Rust_Unnamed_0,
}
#[derive(Copy, Clone)]
#[repr(C)]
pub struct C2Rust_Unnamed_0 {
    pub meta_addr: uint32_t,
    pub addr: uint32_t,
    pub len: size_t,
}
pub type fdb_blob_t = *mut fdb_blob;
pub const SIZE_MAX: ::core::ffi::c_ulong = 18446744073709551615 as ::core::ffi::c_ulong;
pub const false_0: ::core::ffi::c_int = 0 as ::core::ffi::c_int;
pub const FDB_WRITE_GRAN: ::core::ffi::c_int = 1 as ::core::ffi::c_int;
pub const FDB_BYTE_ERASED: ::core::ffi::c_int = 0xff as ::core::ffi::c_int;
pub const FDB_BYTE_WRITTEN: ::core::ffi::c_int = 0 as ::core::ffi::c_int;
static mut crc32_table: [uint32_t; 256] = [
    0 as uint32_t,
    0x77073096 as uint32_t,
    0xee0e612c as uint32_t,
    0x990951ba as uint32_t,
    0x76dc419 as uint32_t,
    0x706af48f as uint32_t,
    0xe963a535 as uint32_t,
    0x9e6495a3 as uint32_t,
    0xedb8832 as uint32_t,
    0x79dcb8a4 as uint32_t,
    0xe0d5e91e as uint32_t,
    0x97d2d988 as uint32_t,
    0x9b64c2b as uint32_t,
    0x7eb17cbd as uint32_t,
    0xe7b82d07 as uint32_t,
    0x90bf1d91 as uint32_t,
    0x1db71064 as uint32_t,
    0x6ab020f2 as uint32_t,
    0xf3b97148 as uint32_t,
    0x84be41de as uint32_t,
    0x1adad47d as uint32_t,
    0x6ddde4eb as uint32_t,
    0xf4d4b551 as uint32_t,
    0x83d385c7 as uint32_t,
    0x136c9856 as uint32_t,
    0x646ba8c0 as uint32_t,
    0xfd62f97a as uint32_t,
    0x8a65c9ec as uint32_t,
    0x14015c4f as uint32_t,
    0x63066cd9 as uint32_t,
    0xfa0f3d63 as uint32_t,
    0x8d080df5 as uint32_t,
    0x3b6e20c8 as uint32_t,
    0x4c69105e as uint32_t,
    0xd56041e4 as uint32_t,
    0xa2677172 as uint32_t,
    0x3c03e4d1 as uint32_t,
    0x4b04d447 as uint32_t,
    0xd20d85fd as uint32_t,
    0xa50ab56b as uint32_t,
    0x35b5a8fa as uint32_t,
    0x42b2986c as uint32_t,
    0xdbbbc9d6 as uint32_t,
    0xacbcf940 as uint32_t,
    0x32d86ce3 as uint32_t,
    0x45df5c75 as uint32_t,
    0xdcd60dcf as uint32_t,
    0xabd13d59 as uint32_t,
    0x26d930ac as uint32_t,
    0x51de003a as uint32_t,
    0xc8d75180 as uint32_t,
    0xbfd06116 as uint32_t,
    0x21b4f4b5 as uint32_t,
    0x56b3c423 as uint32_t,
    0xcfba9599 as uint32_t,
    0xb8bda50f as uint32_t,
    0x2802b89e as uint32_t,
    0x5f058808 as uint32_t,
    0xc60cd9b2 as uint32_t,
    0xb10be924 as uint32_t,
    0x2f6f7c87 as uint32_t,
    0x58684c11 as uint32_t,
    0xc1611dab as uint32_t,
    0xb6662d3d as uint32_t,
    0x76dc4190 as uint32_t,
    0x1db7106 as uint32_t,
    0x98d220bc as uint32_t,
    0xefd5102a as uint32_t,
    0x71b18589 as uint32_t,
    0x6b6b51f as uint32_t,
    0x9fbfe4a5 as uint32_t,
    0xe8b8d433 as uint32_t,
    0x7807c9a2 as uint32_t,
    0xf00f934 as uint32_t,
    0x9609a88e as uint32_t,
    0xe10e9818 as uint32_t,
    0x7f6a0dbb as uint32_t,
    0x86d3d2d as uint32_t,
    0x91646c97 as uint32_t,
    0xe6635c01 as uint32_t,
    0x6b6b51f4 as uint32_t,
    0x1c6c6162 as uint32_t,
    0x856530d8 as uint32_t,
    0xf262004e as uint32_t,
    0x6c0695ed as uint32_t,
    0x1b01a57b as uint32_t,
    0x8208f4c1 as uint32_t,
    0xf50fc457 as uint32_t,
    0x65b0d9c6 as uint32_t,
    0x12b7e950 as uint32_t,
    0x8bbeb8ea as uint32_t,
    0xfcb9887c as uint32_t,
    0x62dd1ddf as uint32_t,
    0x15da2d49 as uint32_t,
    0x8cd37cf3 as uint32_t,
    0xfbd44c65 as uint32_t,
    0x4db26158 as uint32_t,
    0x3ab551ce as uint32_t,
    0xa3bc0074 as uint32_t,
    0xd4bb30e2 as uint32_t,
    0x4adfa541 as uint32_t,
    0x3dd895d7 as uint32_t,
    0xa4d1c46d as uint32_t,
    0xd3d6f4fb as uint32_t,
    0x4369e96a as uint32_t,
    0x346ed9fc as uint32_t,
    0xad678846 as uint32_t,
    0xda60b8d0 as uint32_t,
    0x44042d73 as uint32_t,
    0x33031de5 as uint32_t,
    0xaa0a4c5f as uint32_t,
    0xdd0d7cc9 as uint32_t,
    0x5005713c as uint32_t,
    0x270241aa as uint32_t,
    0xbe0b1010 as uint32_t,
    0xc90c2086 as uint32_t,
    0x5768b525 as uint32_t,
    0x206f85b3 as uint32_t,
    0xb966d409 as uint32_t,
    0xce61e49f as uint32_t,
    0x5edef90e as uint32_t,
    0x29d9c998 as uint32_t,
    0xb0d09822 as uint32_t,
    0xc7d7a8b4 as uint32_t,
    0x59b33d17 as uint32_t,
    0x2eb40d81 as uint32_t,
    0xb7bd5c3b as uint32_t,
    0xc0ba6cad as uint32_t,
    0xedb88320 as uint32_t,
    0x9abfb3b6 as uint32_t,
    0x3b6e20c as uint32_t,
    0x74b1d29a as uint32_t,
    0xead54739 as uint32_t,
    0x9dd277af as uint32_t,
    0x4db2615 as uint32_t,
    0x73dc1683 as uint32_t,
    0xe3630b12 as uint32_t,
    0x94643b84 as uint32_t,
    0xd6d6a3e as uint32_t,
    0x7a6a5aa8 as uint32_t,
    0xe40ecf0b as uint32_t,
    0x9309ff9d as uint32_t,
    0xa00ae27 as uint32_t,
    0x7d079eb1 as uint32_t,
    0xf00f9344 as uint32_t,
    0x8708a3d2 as uint32_t,
    0x1e01f268 as uint32_t,
    0x6906c2fe as uint32_t,
    0xf762575d as uint32_t,
    0x806567cb as uint32_t,
    0x196c3671 as uint32_t,
    0x6e6b06e7 as uint32_t,
    0xfed41b76 as uint32_t,
    0x89d32be0 as uint32_t,
    0x10da7a5a as uint32_t,
    0x67dd4acc as uint32_t,
    0xf9b9df6f as uint32_t,
    0x8ebeeff9 as uint32_t,
    0x17b7be43 as uint32_t,
    0x60b08ed5 as uint32_t,
    0xd6d6a3e8 as uint32_t,
    0xa1d1937e as uint32_t,
    0x38d8c2c4 as uint32_t,
    0x4fdff252 as uint32_t,
    0xd1bb67f1 as uint32_t,
    0xa6bc5767 as uint32_t,
    0x3fb506dd as uint32_t,
    0x48b2364b as uint32_t,
    0xd80d2bda as uint32_t,
    0xaf0a1b4c as uint32_t,
    0x36034af6 as uint32_t,
    0x41047a60 as uint32_t,
    0xdf60efc3 as uint32_t,
    0xa867df55 as uint32_t,
    0x316e8eef as uint32_t,
    0x4669be79 as uint32_t,
    0xcb61b38c as uint32_t,
    0xbc66831a as uint32_t,
    0x256fd2a0 as uint32_t,
    0x5268e236 as uint32_t,
    0xcc0c7795 as uint32_t,
    0xbb0b4703 as uint32_t,
    0x220216b9 as uint32_t,
    0x5505262f as uint32_t,
    0xc5ba3bbe as uint32_t,
    0xb2bd0b28 as uint32_t,
    0x2bb45a92 as uint32_t,
    0x5cb36a04 as uint32_t,
    0xc2d7ffa7 as uint32_t,
    0xb5d0cf31 as uint32_t,
    0x2cd99e8b as uint32_t,
    0x5bdeae1d as uint32_t,
    0x9b64c2b0 as uint32_t,
    0xec63f226 as uint32_t,
    0x756aa39c as uint32_t,
    0x26d930a as uint32_t,
    0x9c0906a9 as uint32_t,
    0xeb0e363f as uint32_t,
    0x72076785 as uint32_t,
    0x5005713 as uint32_t,
    0x95bf4a82 as uint32_t,
    0xe2b87a14 as uint32_t,
    0x7bb12bae as uint32_t,
    0xcb61b38 as uint32_t,
    0x92d28e9b as uint32_t,
    0xe5d5be0d as uint32_t,
    0x7cdcefb7 as uint32_t,
    0xbdbdf21 as uint32_t,
    0x86d3d2d4 as uint32_t,
    0xf1d4e242 as uint32_t,
    0x68ddb3f8 as uint32_t,
    0x1fda836e as uint32_t,
    0x81be16cd as uint32_t,
    0xf6b9265b as uint32_t,
    0x6fb077e1 as uint32_t,
    0x18b74777 as uint32_t,
    0x88085ae6 as uint32_t,
    0xff0f6a70 as uint32_t,
    0x66063bca as uint32_t,
    0x11010b5c as uint32_t,
    0x8f659eff as uint32_t,
    0xf862ae69 as uint32_t,
    0x616bffd3 as uint32_t,
    0x166ccf45 as uint32_t,
    0xa00ae278 as uint32_t,
    0xd70dd2ee as uint32_t,
    0x4e048354 as uint32_t,
    0x3903b3c2 as uint32_t,
    0xa7672661 as uint32_t,
    0xd06016f7 as uint32_t,
    0x4969474d as uint32_t,
    0x3e6e77db as uint32_t,
    0xaed16a4a as uint32_t,
    0xd9d65adc as uint32_t,
    0x40df0b66 as uint32_t,
    0x37d83bf0 as uint32_t,
    0xa9bcae53 as uint32_t,
    0xdebb9ec5 as uint32_t,
    0x47b2cf7f as uint32_t,
    0x30b5ffe9 as uint32_t,
    0xbdbdf21c as uint32_t,
    0xcabac28a as uint32_t,
    0x53b39330 as uint32_t,
    0x24b4a3a6 as uint32_t,
    0xbad03605 as uint32_t,
    0xcdd70693 as uint32_t,
    0x54de5729 as uint32_t,
    0x23d967bf as uint32_t,
    0xb3667a2e as uint32_t,
    0xc4614ab8 as uint32_t,
    0x5d681b02 as uint32_t,
    0x2a6f2b94 as uint32_t,
    0xb40bbe37 as uint32_t,
    0xc30c8ea1 as uint32_t,
    0x5a05df1b as uint32_t,
    0x2d02ef8d as uint32_t,
];
#[no_mangle]
pub unsafe extern "C" fn fdb_calc_crc32(
    mut crc: uint32_t,
    mut buf: *const ::core::ffi::c_void,
    mut size: size_t,
) -> uint32_t {
    let mut p: *const uint8_t = ::core::ptr::null::<uint8_t>();
    p = buf as *const uint8_t;
    crc = crc ^ !(0 as uint32_t);
    loop {
        let c2rust_fresh0 = size;
        size = size.wrapping_sub(1);
        if c2rust_fresh0 == 0 {
            break;
        }
        let c2rust_fresh1 = p;
        p = p.offset(1);
        crc = crc32_table[((crc ^ *c2rust_fresh1 as uint32_t) & 0xff as uint32_t) as usize]
            ^ crc >> 8 as ::core::ffi::c_int;
    }
    return crc ^ !(0 as uint32_t);
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_set_status(
    mut status_table: *mut uint8_t,
    mut status_num: size_t,
    mut status_index: size_t,
) -> size_t {
    let mut byte_index: size_t = SIZE_MAX as size_t;
    memset(
        status_table as *mut ::core::ffi::c_void,
        FDB_BYTE_ERASED,
        status_num
            .wrapping_mul(FDB_WRITE_GRAN as size_t)
            .wrapping_add(7 as size_t)
            .wrapping_div(8 as size_t),
    );
    if status_index > 0 as size_t {
        byte_index = status_index
            .wrapping_sub(1 as size_t)
            .wrapping_div(8 as size_t);
        let ref mut c2rust_fresh2 = *status_table.offset(byte_index as isize);
        *c2rust_fresh2 = (*c2rust_fresh2 as ::core::ffi::c_int
            & 0xff as ::core::ffi::c_int >> status_index.wrapping_rem(8 as size_t))
            as uint8_t;
    }
    return byte_index;
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_get_status(
    mut status_table: *mut uint8_t,
    mut status_num: size_t,
) -> size_t {
    let mut i: size_t = 0 as size_t;
    status_num = status_num.wrapping_sub(1);
    let mut status_num_bak: size_t = status_num;
    loop {
        let c2rust_fresh3 = status_num;
        status_num = status_num.wrapping_sub(1);
        if c2rust_fresh3 == 0 {
            break;
        }
        if *status_table.offset(status_num.wrapping_div(8 as size_t) as isize) as ::core::ffi::c_int
            & 0x80 as ::core::ffi::c_int >> status_num.wrapping_rem(8 as size_t)
            == 0 as ::core::ffi::c_int
        {
            break;
        }
        i = i.wrapping_add(1);
    }
    return status_num_bak.wrapping_sub(i);
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_write_status(
    mut db: fdb_db_t,
    mut addr: uint32_t,
    mut status_table: *mut uint8_t,
    mut status_num: size_t,
    mut status_index: size_t,
    mut sync: bool,
) -> fdb_err_t {
    let mut result: fdb_err_t = FDB_NO_ERR;
    let mut byte_index: size_t = 0;
    '_c2rust_label: {
        if status_index < status_num {
        } else {
            __assert_fail(
                b"status_index < status_num\0".as_ptr() as *const ::core::ffi::c_char,
                b"/mnt/f/agent/crustpaper/0630/sources/FlashDB/src/fdb_utils.c\0"
                    .as_ptr() as *const ::core::ffi::c_char,
                152 as ::core::ffi::c_uint,
                b"fdb_err_t _fdb_write_status(fdb_db_t, uint32_t, uint8_t *, size_t, size_t, _Bool)\0"
                    .as_ptr() as *const ::core::ffi::c_char,
            );
        }
    };
    '_c2rust_label_0: {
        if !status_table.is_null() {
        } else {
            __assert_fail(
                b"status_table\0".as_ptr() as *const ::core::ffi::c_char,
                b"/mnt/f/agent/crustpaper/0630/sources/FlashDB/src/fdb_utils.c\0"
                    .as_ptr() as *const ::core::ffi::c_char,
                153 as ::core::ffi::c_uint,
                b"fdb_err_t _fdb_write_status(fdb_db_t, uint32_t, uint8_t *, size_t, size_t, _Bool)\0"
                    .as_ptr() as *const ::core::ffi::c_char,
            );
        }
    };
    byte_index = _fdb_set_status(status_table, status_num, status_index);
    if byte_index == SIZE_MAX as size_t {
        return FDB_NO_ERR;
    }
    result = _fdb_flash_write(
        db,
        (addr as size_t).wrapping_add(byte_index) as uint32_t,
        status_table.offset(byte_index as isize) as *mut uint8_t as *mut uint32_t
            as *const ::core::ffi::c_void,
        1 as size_t,
        sync,
    );
    return result;
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_read_status(
    mut db: fdb_db_t,
    mut addr: uint32_t,
    mut status_table: *mut uint8_t,
    mut total_num: size_t,
) -> size_t {
    '_c2rust_label: {
        if !status_table.is_null() {
        } else {
            __assert_fail(
                b"status_table\0".as_ptr() as *const ::core::ffi::c_char,
                b"/mnt/f/agent/crustpaper/0630/sources/FlashDB/src/fdb_utils.c\0".as_ptr()
                    as *const ::core::ffi::c_char,
                175 as ::core::ffi::c_uint,
                b"size_t _fdb_read_status(fdb_db_t, uint32_t, uint8_t *, size_t)\0".as_ptr()
                    as *const ::core::ffi::c_char,
            );
        }
    };
    _fdb_flash_read(
        db,
        addr,
        status_table as *mut uint32_t as *mut ::core::ffi::c_void,
        total_num
            .wrapping_mul(FDB_WRITE_GRAN as size_t)
            .wrapping_add(7 as size_t)
            .wrapping_div(8 as size_t),
    );
    return _fdb_get_status(status_table, total_num);
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_continue_ff_addr(
    mut db: fdb_db_t,
    mut start: uint32_t,
    mut end: uint32_t,
) -> uint32_t {
    let mut buf: [uint8_t; 32] = [0; 32];
    let mut last_data: uint8_t = FDB_BYTE_WRITTEN as uint8_t;
    let mut i: size_t = 0;
    let mut addr: size_t = start as size_t;
    let mut read_size: size_t = 0;
    while start < end {
        if (start as usize).wrapping_add(::core::mem::size_of::<[uint8_t; 32]>() as usize)
            < end as usize
        {
            read_size = ::core::mem::size_of::<[uint8_t; 32]>() as usize as size_t;
        } else {
            read_size = end.wrapping_sub(start) as size_t;
        }
        _fdb_flash_read(
            db,
            start,
            &raw mut buf as *mut uint8_t as *mut uint32_t as *mut ::core::ffi::c_void,
            read_size,
        );
        i = 0 as size_t;
        while i < read_size {
            if last_data as ::core::ffi::c_int != FDB_BYTE_ERASED
                && buf[i as usize] as ::core::ffi::c_int == FDB_BYTE_ERASED
            {
                addr = (start as size_t).wrapping_add(i);
            }
            last_data = buf[i as usize];
            i = i.wrapping_add(1);
        }
        start = (start as ::core::ffi::c_ulong)
            .wrapping_add(::core::mem::size_of::<[uint8_t; 32]>() as usize as ::core::ffi::c_ulong)
            as uint32_t;
    }
    if last_data as ::core::ffi::c_int == FDB_BYTE_ERASED {
        return addr
            .wrapping_add(
                ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                    as size_t,
            )
            .wrapping_sub(1 as size_t)
            .wrapping_sub(
                addr.wrapping_add(
                    ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                        as size_t,
                )
                .wrapping_sub(1 as size_t)
                .wrapping_rem(
                    ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                        as size_t,
                ),
            ) as uint32_t;
    } else {
        return end;
    };
}
#[no_mangle]
pub unsafe extern "C" fn fdb_blob_make(
    mut blob: fdb_blob_t,
    mut value_buf: *const ::core::ffi::c_void,
    mut buf_len: size_t,
) -> fdb_blob_t {
    (*blob).buf = value_buf as *mut ::core::ffi::c_void;
    (*blob).size = buf_len;
    return blob;
}
#[no_mangle]
pub unsafe extern "C" fn fdb_blob_read(mut db: fdb_db_t, mut blob: fdb_blob_t) -> size_t {
    let mut read_len: size_t = (*blob).size;
    if read_len > (*blob).saved.len {
        read_len = (*blob).saved.len;
    }
    if _fdb_flash_read(db, (*blob).saved.addr, (*blob).buf, read_len) as ::core::ffi::c_uint
        != FDB_NO_ERR as ::core::ffi::c_int as ::core::ffi::c_uint
    {
        read_len = 0 as size_t;
    }
    return read_len;
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_flash_read(
    mut db: fdb_db_t,
    mut addr: uint32_t,
    mut buf: *mut ::core::ffi::c_void,
    mut size: size_t,
) -> fdb_err_t {
    return _fdb_file_read(db, addr, buf, size);
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_flash_erase(
    mut db: fdb_db_t,
    mut addr: uint32_t,
    mut size: size_t,
) -> fdb_err_t {
    return _fdb_file_erase(db, addr, size);
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_flash_write(
    mut db: fdb_db_t,
    mut addr: uint32_t,
    mut buf: *const ::core::ffi::c_void,
    mut size: size_t,
    mut sync: bool,
) -> fdb_err_t {
    return _fdb_file_write(db, addr, buf, size, sync);
}
#[no_mangle]
pub unsafe extern "C" fn _fdb_flash_write_align(
    mut db: fdb_db_t,
    mut addr: uint32_t,
    mut buf: *const uint32_t,
    mut size: size_t,
) -> fdb_err_t {
    let mut result: fdb_err_t = FDB_NO_ERR;
    let mut align_remain: size_t = 0;
    let mut align_data_u8: uint8_t = 0;
    let mut align_data: *mut uint8_t = &raw mut align_data_u8;
    let mut align_data_size: size_t = 1 as size_t;
    memset(
        align_data as *mut ::core::ffi::c_void,
        FDB_BYTE_ERASED,
        align_data_size,
    );
    if size
        .wrapping_div(
            ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                as size_t,
        )
        .wrapping_mul(
            ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                as size_t,
        )
        > 0 as size_t
    {
        result = _fdb_flash_write(
            db,
            addr,
            buf as *const ::core::ffi::c_void,
            size.wrapping_div(
                ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                    as size_t,
            )
            .wrapping_mul(
                ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                    as size_t,
            ),
            false_0 != 0,
        );
    }
    align_remain = size.wrapping_sub(
        size.wrapping_div(
            ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                as size_t,
        )
        .wrapping_mul(
            ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                as size_t,
        ),
    );
    if result as ::core::ffi::c_uint == FDB_NO_ERR as ::core::ffi::c_int as ::core::ffi::c_uint
        && align_remain != 0
    {
        memcpy(
            align_data as *mut ::core::ffi::c_void,
            (buf as *mut uint8_t).offset(
                size.wrapping_div(
                    ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                        as size_t,
                )
                .wrapping_mul(
                    ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                        as size_t,
                ) as isize,
            ) as *const ::core::ffi::c_void,
            align_remain,
        );
        result = _fdb_flash_write(
            db,
            (addr as size_t).wrapping_add(
                size.wrapping_div(
                    ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                        as size_t,
                )
                .wrapping_mul(
                    ((1 as ::core::ffi::c_int + 7 as ::core::ffi::c_int) / 8 as ::core::ffi::c_int)
                        as size_t,
                ),
            ) as uint32_t,
            align_data as *mut uint32_t as *const ::core::ffi::c_void,
            align_data_size,
            false_0 != 0,
        );
    }
    return result;
}

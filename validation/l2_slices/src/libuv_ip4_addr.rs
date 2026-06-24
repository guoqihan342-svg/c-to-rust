use serde::{Deserialize, Serialize};

pub const AF_INET: u16 = 2;
pub const UV_EINVAL: i32 = -22;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Ip4AddrReport {
    pub return_code: i32,
    pub status: &'static str,
    pub family: u16,
    pub port_host: u16,
    pub port_bytes_hex: String,
    pub addr_bytes_hex: String,
}

pub fn uv_ip4_addr(ip: &str, port: i32) -> Ip4AddrReport {
    let port_host = port as u16;
    let parsed = parse_libuv_ipv4(ip);
    let (return_code, status, addr_bytes) = match parsed {
        Some(bytes) => (0, "ok", bytes),
        None => (UV_EINVAL, "invalid", [0, 0, 0, 0]),
    };

    Ip4AddrReport {
        return_code,
        status,
        family: AF_INET,
        port_host,
        port_bytes_hex: bytes_to_hex(&port_host.to_be_bytes()),
        addr_bytes_hex: bytes_to_hex(&addr_bytes),
    }
}

fn parse_libuv_ipv4(ip: &str) -> Option<[u8; 4]> {
    let mut tmp = [0_u8; 4];
    let mut octets = 0_usize;
    let mut index = 0_usize;
    let mut saw_digit = false;

    for byte in ip.bytes() {
        if byte.is_ascii_digit() {
            let digit = u32::from(byte - b'0');
            let value = u32::from(tmp[index]) * 10 + digit;
            if saw_digit && tmp[index] == 0 {
                return None;
            }
            if value > 255 {
                return None;
            }
            tmp[index] = value as u8;
            if !saw_digit {
                if octets == 4 {
                    return None;
                }
                octets += 1;
                saw_digit = true;
            }
        } else if byte == b'.' && saw_digit {
            if octets == 4 {
                return None;
            }
            index += 1;
            tmp[index] = 0;
            saw_digit = false;
        } else {
            return None;
        }
    }

    if octets < 4 {
        return None;
    }

    Some(tmp)
}

fn bytes_to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UvIp4AddrReport {
pub return_code: i32,
pub status: &'static str,
}

pub fn uv_ip4_addr(ip: &str, port: i32) -> UvIp4AddrReport {
let _ = (ip, port);
UvIp4AddrReport { return_code: 0, status: "ok" }
}

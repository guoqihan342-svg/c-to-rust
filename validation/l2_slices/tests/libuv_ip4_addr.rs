use c_to_rust_l2_slices::libuv_ip4_addr::{uv_ip4_addr, UV_EINVAL};

#[test]
fn libuv_ip4_addr_encodes_loopback_and_port_in_network_order() {
    let report = uv_ip4_addr("127.0.0.1", 9123);

    assert_eq!(report.return_code, 0);
    assert_eq!(report.status, "ok");
    assert_eq!(report.family, 2);
    assert_eq!(report.port_host, 9123);
    assert_eq!(report.port_bytes_hex, "23a3");
    assert_eq!(report.addr_bytes_hex, "7f000001");
}

#[test]
fn libuv_ip4_addr_encodes_wildcard_and_broadcast_boundaries() {
    let wildcard = uv_ip4_addr("0.0.0.0", 0);
    assert_eq!(wildcard.return_code, 0);
    assert_eq!(wildcard.port_bytes_hex, "0000");
    assert_eq!(wildcard.addr_bytes_hex, "00000000");

    let broadcast = uv_ip4_addr("255.255.255.255", 65535);
    assert_eq!(broadcast.return_code, 0);
    assert_eq!(broadcast.port_host, 65535);
    assert_eq!(broadcast.port_bytes_hex, "ffff");
    assert_eq!(broadcast.addr_bytes_hex, "ffffffff");
}

#[test]
fn libuv_ip4_addr_rejects_upstream_invalid_ipv4_cases() {
    for ip in ["255.255.255*000", "255.255.255.256", "2555.0.0.0", "255"] {
        let report = uv_ip4_addr(ip, 9123);
        assert_eq!(report.return_code, UV_EINVAL, "{ip}");
        assert_eq!(report.status, "invalid", "{ip}");
        assert_eq!(report.family, 2, "{ip}");
        assert_eq!(report.port_bytes_hex, "23a3", "{ip}");
        assert_eq!(report.addr_bytes_hex, "00000000", "{ip}");
    }
}

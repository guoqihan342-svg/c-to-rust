# libuv ip4-addr L3 summary

- status: passed
- slice: `uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr)`
- pointer surface: C string pointer input plus sockaddr_in output pointer
- claim: only committed fixture behavior fields; no event-loop/socket/IPv6/full-libuv claim

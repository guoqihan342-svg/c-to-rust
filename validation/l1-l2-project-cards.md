# L1/L2 Project Cards

中文：这些项目卡片把 L0 catalog 目标转成后续可执行动作。它们不是 L1/L2 已通过证据；只有实际 clone、pin commit、build/test、迁移切片编译、C/Rust diff 全部完成后，才能升级对应项目状态。

English: these cards translate L0 catalog targets into executable next steps. They are not L1/L2 evidence by themselves; a project can only be promoted after a pinned clone, native build/test, bounded Rust slice build, and C/Rust differential evidence.

## Execution Rules

- Run large upstream builds outside this repository, preferably in Linux or WSL.
- Pin every upstream repository before L1/L2 work. Use the recorded `head_sha` from `validation/evidence/catalog-remote-probe.json` or a release tag, then store the selected SHA in the per-project evidence file.
- Keep the first Rust slice small and pure where possible. Avoid event loops, scheduler timing, full codecs, cryptographic primitives, allocators in production mode, and server lifecycle code until helper slices pass.
- Every L2 slice must have a native C oracle with stable JSON, text, or binary fixture output. L3 equivalence claims require Rust output diffed against that oracle.

## Priority Order

1. SQLite, zstd, libuv, libevent, Lua, zlib-ng: small helper slices with strong native oracles.
2. Valkey or Redis, curl, Git, nginx, libpng, libjpeg-turbo: parser/format slices with useful complexity.
3. PostgreSQL, OpenSSL, Mbed TLS, FFmpeg, jemalloc, MicroPython, tmux: valuable but require tighter scoping.
4. Zephyr and FreeRTOS-Kernel: keep for RTOS validation after the non-RTOS pipeline is stable.

## First Wave Detailed Cards

### SQLite

- L1 native smoke: `./configure --disable-shared && make sqlite3`, then `./sqlite3 :memory: "select 1;"`.
- L2 Rust slice: `sqlite3PutVarint`/`sqlite3GetVarint`, checksum/hash helper, or another VFS-independent utility before pager/btree work.
- Oracle: C helper emits `{ "encoded_hex": "...", "decoded_value": n, "bytes_used": n, "rc": n }`; CLI SQL transcript fixtures cover higher-level smoke.
- Risk: generated parser and pager invariants are too broad for an early slice.

### zstd

- L1 native smoke: `make -j2` and `make shortest` or `make check` when time allows.
- L2 Rust slice: `lib/common/xxhash.c`, frame header parsing, or a small bitstream reader.
- Oracle: fixed corpus through native `zstd`/`libzstd`; for headers, emit frame metadata JSON.
- Risk: compressed bytes can vary with parameters and CPU paths, so pin level/options/CPU-dispatch settings.

### libuv

- L1 native smoke: `cmake -S . -B build -DBUILD_TESTING=ON && cmake --build build --parallel 2`, then `build/uv_run_tests_a ip4_addr` and `build/uv_run_tests_a ip_name` where available.
- L2 Rust slice: `uv_ip4_addr`, `uv_ip6_addr`, `uv_ip4_name`, `uv_ip6_name`, `uv_inet_pton`, `uv_inet_ntop`.
- Oracle: C helper emits return code, family, port, binary bytes, and round-trip name for IPv4/IPv6 fixtures.
- Risk: callback lifetimes, loop handles, and platform error-code differences are later gates.

### libevent

- L1 native smoke: `cmake -S . -B build -DEVENT__DISABLE_OPENSSL=ON && cmake --build build --parallel 2`, then `ctest --test-dir build -R regress --output-on-failure`.
- L2 Rust slice: `evbuffer` add/remove/drain/search/copyout, or `evhttp_uri_parse`/join.
- Oracle: C helper executes buffer operation scripts and emits length, read bytes, search position, and error code.
- Risk: event backends, thread locks, OpenSSL, and bufferevent lifecycle should stay out of the first slice.

### Lua

- L1 native smoke: `make linux` or platform equivalent, then `./lua -e "print(1+1)"`.
- L2 Rust slice: lexer token helper, string table utility, or small numeric/string parser.
- Oracle: native CLI script output plus C helper for token fixtures when internal APIs are needed.
- Risk: GC and VM stack behavior are not first-slice candidates.

### zlib-ng

- L1 native smoke: `cmake -S . -B build -DZLIB_COMPAT=ON && cmake --build build`, then `ctest --test-dir build --output-on-failure`.
- L2 Rust slice: Adler32/CRC32 scalar fallback before inflate/deflate state machines.
- Oracle: known-answer checksum vectors with native helper output.
- Risk: SIMD dispatch and compression state machines need deeper gate coverage.

## Second Wave Detailed Cards

### Valkey / Redis

- L1 native smoke: `make MALLOC=libc BUILD_TLS=no`, then `src/valkey-server --test-memory 2` or `src/redis-server --test-memory 2`.
- L2 Rust slice: SDS string utility, RESP argv/parser helper, or command table lookup.
- Oracle: RESP transcripts or C helper output for parser state, command arity, and error cases.
- Risk: server lifecycle, forked persistence, replication, cluster, and module ABI should be deferred.

### curl

- L1 native smoke: `autoreconf -fi && ./configure --without-ssl --without-libpsl --disable-shared && make -j2`, then `src/curl --version`; minimal test: `cd tests && ./runtests.pl -n 1`.
- L2 Rust slice: URL component parser via `curl_url_set/get`, or `curl_easy_escape/unescape`.
- Oracle: C helper emits scheme, host, port, path, query, byte-level escape output, and native error code.
- Risk: TLS, IDN, locale, Windows encoding, and protocol matrix should be disabled in early gates.

### Git

- L1 native smoke: `make NO_GETTEXT=YesPlease NO_TCLTK=YesPlease NO_PERL=YesPlease NO_CURL=YesPlease NO_EXPAT=YesPlease`, then `bin-wrappers/git --version`, `git init`, and `git hash-object`.
- L2 Rust slice: object-id hex parser, pkt-line parser, or pathspec helper.
- Oracle: native plumbing commands and fixed object/hash/path fixtures.
- Risk: repository state and platform-specific filesystem rules must be pinned.

### nginx

- L1 native smoke: `auto/configure --with-debug --without-http_rewrite_module --without-http_gzip_module && make -j2`, then `mkdir -p logs && objs/nginx -t -p "$PWD/" -c conf/nginx.conf`.
- L2 Rust slice: `src/core/ngx_string.c` URI escape/unescape first; later `src/http/ngx_http_parse.c` request-line/header parser.
- Oracle: C helper feeds raw URI, request-line, and header corpus and emits JSON.
- Risk: module ABI, memory pools, event loop, and dynamic modules are later gates.

### libpng

- L1 native smoke: CMake build with tests or autotools build after `./autogen.sh`; then `ctest` or `make check`.
- L2 Rust slice: PNG signature/chunk length/type/CRC parser or Paeth/filter helper.
- Oracle: pngtest/pngsuite metadata plus native helper JSON for chunk sequence and CRC results.
- Risk: full image decoding and zlib interaction require pinned fixture suites.

### libjpeg-turbo

- L1 native smoke: `cmake -S . -B build -G "Unix Makefiles" -DWITH_SIMD=0 && cmake --build build --parallel 2`, then `ctest --test-dir build --output-on-failure`.
- L2 Rust slice: scalar RGB/YCbCr conversion, JPEG marker parser, or Huffman table helper.
- Oracle: `cjpeg`/`djpeg` or TurboJPEG tests; compare decoded PPM/raw pixels with exact or tolerance-based rules.
- Risk: SIMD, DCT precision, and codec tolerance need explicit policy before equivalence claims.

## Third Wave Detailed Cards

### PostgreSQL

- L1 native smoke: `./configure --without-readline --without-zlib --prefix=$PWD/install`, then `make -C src/bin/pg_config` and `src/bin/pg_config/pg_config --version`.
- L2 Rust slice: `src/common` checksum, `StringInfo`, or small frontend utility.
- Oracle: C helper for utility vectors; native frontend command output for smoke.
- Risk: parser, planner, backend process model, WAL, and storage semantics are later gates.

### OpenSSL

- L1 native smoke: `./Configure no-shared no-module`, then `make -j2` and a targeted `make test` subset when available.
- L2 Rust slice: non-secret base64/hex/DER length/ASN.1 tag parser only.
- Oracle: KAT fixtures and CLI checks such as `openssl asn1parse`, `dgst`, and `enc -base64`.
- Risk: constant-time code, provider/FIPS behavior, entropy, and ABI compatibility require security-specific gates.

### Mbed TLS

- L1 native smoke: CMake or Make build with tests, then a targeted `ctest` or suite run.
- L2 Rust slice: `library/base64.c`, PEM parser, or non-secret X.509/ASN.1 helper.
- Oracle: `tests/suites` vectors and C helper output.
- Risk: TLS protocol and secret-dependent primitives are later gated.

### FFmpeg

- L1 native smoke: `./configure --disable-everything --disable-doc --disable-x86asm --enable-ffmpeg --enable-ffprobe --enable-protocol=file --enable-demuxer=wav --enable-decoder=pcm_s16le --enable-muxer=null`, then `make -j2 ffmpeg ffprobe` and `./ffmpeg -version`.
- L2 Rust slice: libavutil base64/CRC/Adler helper, WAV/RIFF metadata parser, or small bitstream helper.
- Oracle: `ffprobe -of json`, `framecrc`, `framemd5`, and `-bitexact` fixtures with CPU flags recorded.
- Risk: codec matrices, SIMD, timestamps, and undefined behavior require narrow fixtures.

### jemalloc

- L1 native smoke: release tarball `./configure --disable-shared --disable-cxx && make -j2`; git checkout path may require `./autogen.sh`; then `make check_unit`.
- L2 Rust slice: size-class helper or bitmap utility.
- Oracle: `nallocx`/`sallocx` and native unit helper outputs.
- Risk: allocator concurrency, atomics, arenas, and integration into a process allocator are later gates.

### MicroPython

- L1 native smoke: `make -C mpy-cross`, `make -C ports/unix submodules`, `make -C ports/unix`, then `ports/unix/build-standard/micropython -c "print(1+1)"`.
- L2 Rust slice: qstr/hash helper, lexer token helper, or small `py/` runtime utility.
- Oracle: native unix-port script output plus C helper for qstr/lexer fixtures.
- Risk: generated qstrs, GC, VM stack, and per-port configuration need careful pinning.

### tmux

- L1 native smoke: `sh autogen.sh && ./configure && make -j2 && ./tmux -V`; optional smoke: `TERM=xterm ./tmux -L c2r-smoke -f /dev/null new-session -d -s smoke "sleep 1"` followed by `has-session` and `kill-server`.
- L2 Rust slice: `key-string.c`, UTF-8/grid helper, or command parser subset.
- Oracle: CLI/control-mode fixtures and C helper output for key/UTF-8/parser cases.
- Risk: PTY, terminal width, locale, timing, shell behavior, libevent, ncurses, and yacc dependencies affect reproducibility.

## RTOS Cards

### Zephyr

- L1 native smoke: `west build -b qemu_x86 samples/hello_world`, then `west build -t run`.
- L2 Rust slice: ring buffer, list helper, Kconfig/devicetree-independent parser, or small subsystem utility.
- Oracle: ztest output or QEMU sample logs normalized into stable text/JSON.
- Risk: west multi-repo workspace, generated config, interrupts, scheduling, and multi-architecture behavior.

### FreeRTOS-Kernel

- L1 native smoke: POSIX or simulator port build through CMake, then targeted kernel unit/demo smoke.
- L2 Rust slice: list helper, queue helper, or portable-independent utility before scheduler semantics.
- Oracle: native unit/vector helper output with scheduler-free fixtures.
- Risk: critical sections, interrupts, task scheduling, and port layers require RTOS-aware gates.

## Reporting Rule

For a future claim such as "12+ complex C projects validated", require at least:

- L0 passed for all named projects.
- L1 native build/test smoke passed for all named projects.
- L2 bounded Rust slice compiled for all named projects.
- L3 C/Rust differential evidence for any project claimed semantically equivalent.

If a project has only L0 evidence, report it as "cataloged and remotely probed", not migrated.

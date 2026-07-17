from __future__ import annotations

import re


_SYSTEM_EXACT = {
    "--shared", "-export-dynamic", "-nodefaultlibs", "-no-pie", "-nostartfiles",
    "-nostdlib", "-pie", "-pthread", "-pthreads", "-rdynamic", "-s", "-shared",
    "-static", "-static-libgcc", "-static-libstdc++", "/DLL",
}
_FORWARDED_EXACT = {
    "--build-id", "--eh-frame-hdr", "--export-dynamic", "--fatal-warnings",
    "--gc-sections", "--no-export-dynamic", "--no-gc-sections",
    "--no-undefined", "--strip-all", "--warn-common", "-E", "-S", "-s",
}
_Z_KEYWORDS = {
    "combreloc", "defs", "execstack", "global", "initfirst", "interpose",
    "lazy", "muldefs", "nocombreloc", "nocopyreloc", "nodefaultlib",
    "nodelete", "nodlopen", "nodump", "noexecstack", "norelro", "now",
    "origin", "pack-relative-relocs", "relro", "separate-code", "text", "notext",
}
_LIBRARY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}$")
_ENTRY = re.compile(
    r"^(?:0x[0-9A-Fa-f]+|[0-9]+|[A-Za-z_.$][A-Za-z0-9_.$@-]{0,254})$"
)
_Z_ASSIGNMENT = re.compile(
    r"^(?:common-page-size|max-page-size|stack-size)="
    r"(?:0x[0-9A-Fa-f]+|[1-9][0-9]*)$"
)


def supported_system_link_argument(value: str) -> bool:
    if value in _SYSTEM_EXACT or value.casefold() == "/dll":
        return True
    if value.startswith("-l:"):
        return _LIBRARY.fullmatch(value[3:]) is not None
    if value.startswith("-l"):
        return _LIBRARY.fullmatch(value[2:]) is not None
    if value.upper().startswith("/DEFAULTLIB:"):
        return _LIBRARY.fullmatch(value[len("/DEFAULTLIB:"):]) is not None
    if not value.startswith("-Wl,") or "@" in value:
        return False
    parts = value[4:].split(",")
    if len(parts) == 1:
        item = parts[0]
        build_id = item.split("=", 1)[1] if item.startswith("--build-id=") else None
        return (
            item in _FORWARDED_EXACT
            or build_id in {"md5", "none", "sha1", "uuid"}
            or isinstance(build_id, str)
            and re.fullmatch(r"0x[0-9A-Fa-f]+", build_id) is not None
            or item.startswith("--hash-style=")
            and item.split("=", 1)[1] in {"both", "gnu", "sysv"}
            or item.startswith("-l") and supported_system_link_argument(item)
        )
    if len(parts) != 2:
        return False
    option, argument = parts
    if option == "-z":
        return argument in _Z_KEYWORDS or _Z_ASSIGNMENT.fullmatch(argument) is not None
    if option in {"-soname", "--soname", "-m", "--emulation"}:
        return _LIBRARY.fullmatch(argument) is not None
    if option in {"-e", "--entry"}:
        return _ENTRY.fullmatch(argument) is not None
    return False


__all__ = ["supported_system_link_argument"]

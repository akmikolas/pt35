#!/usr/bin/env python3
"""严格扫描：只判定"应该是 ELF"的文件，排除所有已知的文本/脚本类型

用法: strict-scan.py <根目录>
"""
import os
import sys

ELF = b"\x7fELF"

# 这些路径/扩展名不可能是 ELF
EXCLUDE_DIR_PARTS = (
    "/usr/share/", "/etc/", "/var/", "/usr/include/", "/usr/src/",
    "/usr/lib/modules/", "/usr/lib/firmware/", "/usr/lib/ldscripts/",
    "/usr/lib/systemd/system/", "/usr/lib/systemd/user/",
    "/usr/lib/systemd/network/", "/usr/lib/node_modules/",
    "/usr/lib/python", "/usr/lib/perl", "/usr/lib/cmake/",
    "/usr/share/doc/", "/usr/share/man/",
)
EXCLUDE_EXT = (
    ".conf", ".socket", ".service", ".target", ".timer", ".mount", ".txt",
    ".md", ".json", ".xml", ".desktop", ".pc", ".h", ".py", ".sh", ".pl",
    ".vim", ".rules", ".list", ".preset", ".path", ".slice", ".scope",
    ".device", ".swap", ".network", ".link", ".nspawn", ".tmpfile",
    ".journal", ".a", ".o", ".mo", ".po", ".cfg", ".ini", ".toml",
    ".yaml", ".yml", ".tsv", ".csv", ".js", ".lua", ".rb", ".el",
    ".dict", ".main.dict", ".softdep", ".alias", ".builtin", ".order",
    ".symbols", ".devname", ".modules", ".bin", ".dat", ".txt", ".sig",
)


def is_elf_candidate(path):
    for part in EXCLUDE_DIR_PARTS:
        if part in path:
            return False
    base = os.path.basename(path)
    if ".so" in base:
        return True
    if base.endswith(EXCLUDE_EXT):
        return False
    if ".conf" in base or base.endswith("~"):
        return False
    # bin/sbin 下的无扩展名文件，或可执行位
    if "/bin/" in path or "/sbin/" in path:
        return "." not in base
    return False


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "/mnt/pt35root"
    corrupt = []
    scanned = 0
    for sub in ("usr/bin", "usr/sbin", "usr/lib", "usr/libexec"):
        base_dir = os.path.join(root, sub)
        if not os.path.isdir(base_dir):
            continue
        for dp, dn, fns in os.walk(base_dir):
            # 跳过排除目录（加速）
            if any(p in dp + "/" for p in EXCLUDE_DIR_PARTS):
                continue
            for fn in fns:
                p = os.path.join(dp, fn)
                if not is_elf_candidate(p):
                    continue
                try:
                    if os.path.islink(p) or not os.path.isfile(p):
                        continue
                    st = os.stat(p)
                    if st.st_size < 64:
                        continue
                    with open(p, "rb") as f:
                        head = f.read(64)
                except OSError:
                    continue
                scanned += 1
                if head[:4] == ELF:
                    continue
                if any(m in head for m in (b"GNU ld script", b"GROUP (", b"INPUT (")):
                    continue
                if head and all(32 <= c < 127 or c in (9, 10, 13) for c in head[:48]):
                    continue
                corrupt.append((p.replace(root, ""), os.path.getsize(p), head[:8].hex()))

    print("  严格扫描 %d 个 ELF 候选文件" % scanned)
    if not corrupt:
        print("  ✅ 未发现损坏")
        return 0
    print("  ❌ 损坏 %d 个：" % len(corrupt))
    for p, s, h in corrupt:
        print("    %-50s %9d B  head=%s" % (p, s, h))
    return 1


if __name__ == "__main__":
    sys.exit(main())

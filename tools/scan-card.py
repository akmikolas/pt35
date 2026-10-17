#!/usr/bin/env python3
"""扫描已挂载的 SD 卡根分区，找出损坏的二进制/共享库

判定：应该是 ELF 的文件（bin/sbin/.so）前 4 字节不是 \x7fELF，
且不是 GNU ld 链接脚本、不是文本文件 → 判为损坏。
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/mnt/pt35root"
ELF = b"\x7fELF"
SCRIPT_MARKERS = (b"GNU ld script", b"GROUP (", b"INPUT (", b"OUTPUT_FORMAT")

# 明确不该是 ELF 的扩展名
NOT_BINARY_EXT = (
    ".conf", ".socket", ".service", ".target", ".timer", ".mount", ".txt", ".md",
    ".json", ".xml", ".desktop", ".pc", ".h", ".py", ".sh", ".pl", ".vim", ".rules",
    ".list", ".preset", ".path", ".slice", ".scope", ".device", ".swap", ".network",
    ".link", ".nspawn", ".tmpfile", ".journal", ".gz", ".xz", ".zst", ".a", ".o",
    ".mo", ".po", ".pot", ".cfg", ".ini", ".toml", ".yaml", ".yml", ".tsv", ".csv",
)


def is_candidate(path):
    base = os.path.basename(path)
    # .so / .so.1 一定是二进制
    if ".so" in base:
        return True
    if base.endswith(NOT_BINARY_EXT):
        return False
    if "/bin/" in path or "/sbin/" in path:
        return True
    if "." not in base:          # 无扩展名 → 可能是可执行文件
        return True
    return False


def main():
    corrupt = []
    scanned = 0
    for sub in ("usr/bin", "usr/sbin", "usr/lib", "bin", "sbin", "lib", "usr/libexec"):
        base = os.path.join(ROOT, sub)
        if not os.path.isdir(base):
            continue
        for dp, dn, fns in os.walk(base):
            for fn in fns:
                p = os.path.join(dp, fn)
                if not is_candidate(p):
                    continue
                try:
                    if os.path.islink(p) or not os.path.isfile(p):
                        continue
                    with open(p, "rb") as f:
                        head = f.read(64)
                except OSError:
                    continue
                scanned += 1
                if head[:4] == ELF:
                    continue
                if any(m in head for m in SCRIPT_MARKERS):
                    continue
                # 纯 ASCII 文本（配置类）
                if head and all(32 <= c < 127 or c in (9, 10, 13) for c in head[:48]):
                    continue
                try:
                    size = os.path.getsize(p)
                except OSError:
                    size = -1
                corrupt.append((p.replace(ROOT, ""), size, head[:8].hex()))

    print("  扫描候选文件 %d 个" % scanned)
    if not corrupt:
        print("  ✅ 未发现损坏")
        return 0
    print("  ❌ 发现损坏 %d 个：" % len(corrupt))
    for p, s, h in corrupt:
        print("    %-52s %8d B  head=%s" % (p, s, h))
    return 1


if __name__ == "__main__":
    sys.exit(main())

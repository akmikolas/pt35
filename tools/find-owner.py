#!/usr/bin/env python3
"""从 pacman 本地数据库查文件归属包（正确处理 files 段格式）

pacman 的 files 文件格式:
    %FILES%
    usr/lib/libfoo.so.1        ← 注意：没有前导 /
    usr/bin/foo
    (空行)
"""
import os
import sys


def owner_map(targets):
    """返回 {文件路径: [包名,...]}"""
    found = {t: [] for t in targets}
    localdb = "/var/lib/pacman/local"
    for entry in sorted(os.listdir(localdb)):
        fp = os.path.join(localdb, entry, "files")
        if not os.path.isfile(fp):
            continue
        pkg = entry.rsplit("-", 2)[0]
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for line in lines:
            if not line or line.startswith("%"):
                continue
            cand = "/" + line.lstrip("/")
            if cand in found:
                found[cand].append(f"{pkg} ({entry})")
    return found


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "/usr/lib/libutil.so.1",
        "/usr/lib/libacl.so.1.2.2400",
        "/usr/bin/ssh",
        "/usr/bin/sshd",
        "/usr/bin/pacman",
    ]
    res = owner_map(targets)
    for t in targets:
        pkgs = res.get(t, [])
        print(f"  {t}")
        print(f"    → {', '.join(pkgs) if pkgs else '❌ 未找到归属（可能是 .so 版本化文件，用 SONAME 查）'}")

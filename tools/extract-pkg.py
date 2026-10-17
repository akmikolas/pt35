#!/usr/bin/env python3
"""从 Arch 包 (.pkg.tar.xz) 中提取指定文件并校验

用法: extract-pkg.py <包文件> <目标目录> <文件名匹配子串> [更多子串...]
"""
import os
import shutil
import sys
import tarfile

ELF = b"\x7fELF"


def describe(path):
    if os.path.islink(path):
        return "symlink -> %s" % os.readlink(path)
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        n = os.path.getsize(path)
        kind = "ELF-OK" if head == ELF else "NOT-ELF(%s)" % head.hex()
        return "%d bytes  %s" % (n, kind)
    except OSError as e:
        return "读取失败: %s" % e


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    pkg, outdir = sys.argv[1], sys.argv[2]
    patterns = sys.argv[3:]

    if not os.path.isfile(pkg):
        print("  [FAIL] 包文件不存在: %s" % pkg)
        return 1

    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir, exist_ok=True)

    # 用 r:* 自动识别压缩格式（xz / zst / gz 皆可）
    with tarfile.open(pkg, "r:*") as t:
        members = [m for m in t.getmembers()
                   if any(pat in m.name for pat in patterns)]
        members = [m for m in members if m.isfile() or m.issym()]
        if not members:
            print("  [FAIL] 包内未找到匹配 %s 的成员" % patterns)
            return 1
        print("  包内匹配成员:")
        for m in members:
            print("    %-52s %8d B  type=%s" % (m.name, m.size, m.type.decode()))
        t.extractall(outdir, members=members)

    print("  已提取到: %s" % outdir)
    print("  提取结果:")
    n_ok = 0
    for dp, dn, fns in os.walk(outdir):
        for fn in fns:
            p = os.path.join(dp, fn)
            print("    %-52s %s" % (p, describe(p)))
            if not os.path.islink(p) and os.path.basename(p).endswith(".so.1"):
                n_ok += 1
    print("  [OK] 提取完成" if n_ok else "  [WARN] 未提取到 .so.1 文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())

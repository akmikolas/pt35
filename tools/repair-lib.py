#!/usr/bin/env python3
"""从已提取的包内容修复损坏的系统库（原子替换 + 备份 + 校验）

用法: repair-lib.py <源文件> <目标文件>
"""
import os
import shutil
import sys

ELF = b"\x7fELF"


def elf_ok(p):
    try:
        with open(p, "rb") as f:
            return f.read(4) == ELF
    except OSError:
        return False


def size(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return -1


def main():
    if len(sys.argv) < 3:
        print("用法: repair-lib.py <源文件> <目标文件>")
        return 2
    src, dst = sys.argv[1], sys.argv[2]

    if not os.path.exists(src):
        print("  [FAIL] 源文件不存在: %s" % src)
        return 1
    if not elf_ok(src):
        print("  [FAIL] 源文件不是合法 ELF: %s" % src)
        return 1

    print("  修复前:")
    print("    源   %s: %s %d 字节" % (src, "ELF" if elf_ok(src) else "非ELF", size(src)))
    if os.path.exists(dst):
        print("    目标 %s: %s %d 字节" % (dst, "ELF" if elf_ok(dst) else "损坏", size(dst)))
    else:
        print("    目标 %s: 不存在（将新建）" % dst)

    bak = dst + ".corrupt-backup"
    if os.path.exists(dst) and not os.path.exists(bak):
        shutil.copy2(dst, bak)
        print("    已备份损坏文件 -> %s" % bak)

    tmp = os.path.join(os.path.dirname(dst), "." + os.path.basename(dst) + ".new")
    shutil.copy2(src, tmp)
    os.chmod(tmp, 0o755)
    os.replace(tmp, dst)

    ok = elf_ok(dst)
    print("  修复后:")
    print("    目标 %s: %s %d 字节" % (dst, "ELF" if ok else "损坏", size(dst)))
    print("  %s" % ("[OK] 修复成功" if ok else "[FAIL] 修复后仍不是 ELF"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

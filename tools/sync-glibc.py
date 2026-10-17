#!/usr/bin/env python3
"""把解包好的 glibc 文件同步到 SD 卡，只覆盖【损坏】的文件

好处：
  1. 只写必要文件，减少 SD 卡写入量（该卡写入可靠性存疑）
  2. 自动统计，输出清晰
  3. 覆盖前备份为 .corrupt-<ts>
"""
import os
import shutil
import sys
import time

SRC = "/tmp/glibc-full"
DST = "/mnt/pt35root"
ELF = b"\x7fELF"


def is_elf(path, size=4):
    try:
        with open(path, "rb") as f:
            return f.read(size) == ELF
    except OSError:
        return False


def main():
    ts = time.strftime("%m%d-%H%M%S")
    fixed = []
    already_ok = 0
    skipped = 0
    failed = []

    for dp, dn, fns in os.walk(SRC):
        for fn in fns:
            src = os.path.join(dp, fn)
            rel = os.path.relpath(src, SRC)
            dst = os.path.join(DST, rel)
            if not os.path.isfile(src):
                continue
            if not os.path.exists(dst):
                # 目标不存在 → 属于"缺失"，也补上
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    fixed.append((rel, "缺失→已补"))
                except OSError as e:
                    failed.append((rel, str(e)))
                continue
            if is_elf(dst):
                already_ok += 1
                continue
            # 目标损坏 → 备份 + 覆盖
            try:
                bak = dst + ".corrupt-" + ts
                if not os.path.exists(bak):
                    shutil.copy2(dst, bak)
                shutil.copy2(src, dst)
                os.chmod(dst, 0o755)
                if is_elf(dst):
                    fixed.append((rel, "损坏→已修复"))
                else:
                    failed.append((rel, "覆盖后仍非 ELF"))
            except OSError as e:
                failed.append((rel, str(e)))

    print("  已正确的文件: %d（未改动，减少写入）" % already_ok)
    print("  修复/补齐:    %d" % len(fixed))
    for rel, why in fixed:
        print("    %-50s %s" % (rel, why))
    if failed:
        print("  ❌ 失败 %d:" % len(failed))
        for rel, why in failed:
            print("    %-50s %s" % (rel, why))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

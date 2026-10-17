#!/usr/bin/env python3
"""从下载好的 Arch 包修复 SD 卡上的损坏文件

用法: repair-from-pkgs.py <包目录> <SD卡根> [--dry-run]

策略：
  1. 解包所有 .pkg.tar.* 到临时目录
  2. 与卡上文件逐一比对（大小 + SHA256）
  3. 只覆盖【内容不同】的文件，并备份原文件
  4. 跳过 .PKGINFO / .INSTALL 等元数据
"""
import hashlib
import os
import shutil
import sys
import tarfile
import time

SKIP_NAMES = (".PKGINFO", ".INSTALL", ".MTREE", ".BUILDINFO", ".Changelog")
SKIP_PREFIX = (".",)


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


def same_file(a, b):
    """大小相同且 sha256 相同才算相同"""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
    except OSError:
        return False
    return sha256(a) == sha256(b)


def extract_all(pkgdir, dest):
    os.makedirs(dest, exist_ok=True)
    pkgs = sorted(f for f in os.listdir(pkgdir)
                  if ".pkg.tar" in f and not f.endswith(".sig"))
    n = 0
    for p in pkgs:
        try:
            with tarfile.open(os.path.join(pkgdir, p), "r:*") as t:
                for m in t.getmembers():
                    base = os.path.basename(m.name)
                    if base in SKIP_NAMES or base.startswith(SKIP_PREFIX):
                        continue
                    if not (m.isfile() or m.issym()):
                        continue
                    t.extract(m, dest)
                    n += 1
        except Exception as e:
            print("  [WARN] %s 解包失败: %s" % (p, e))
    return len(pkgs), n


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    pkgdir, cardroot = sys.argv[1], sys.argv[2]
    dry = "--dry-run" in sys.argv[3:]

    staging = "/tmp/pt35-staging"
    shutil.rmtree(staging, ignore_errors=True)
    print("  解包 %s ..." % pkgdir)
    npkg, nfile = extract_all(pkgdir, staging)
    print("  解包 %d 个包，%d 个文件" % (npkg, nfile))
    print()

    ts = time.strftime("%m%d-%H%M%S")
    fixed, ok, missing, failed = [], 0, [], []

    for dp, dn, fns in os.walk(staging):
        for fn in fns:
            src = os.path.join(dp, fn)
            rel = os.path.relpath(src, staging)
            dst = os.path.join(cardroot, rel)

            if not os.path.exists(dst):
                missing.append(rel)
                if not dry:
                    try:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                    except OSError as e:
                        failed.append((rel, str(e)))
                continue

            if same_file(src, dst):
                ok += 1
                continue

            # 内容不同 → 修复
            fixed.append(rel)
            if not dry:
                try:
                    bak = dst + ".bad-" + ts
                    if not os.path.exists(bak):
                        shutil.copy2(dst, bak)
                    shutil.copy2(src, dst)
                    os.chmod(dst, os.stat(src).st_mode & 0o7777)
                except OSError as e:
                    failed.append((rel, str(e)))

    print("  已正确（未改动）: %d" % ok)
    print("  需修复:          %d" % len(fixed))
    for r in fixed:
        print("    FIX  %s" % r)
    if missing:
        print("  卡上缺失（补齐）: %d" % len(missing))
        for r in missing[:20]:
            print("    ADD  %s" % r)
        if len(missing) > 20:
            print("    ... 还有 %d 个" % (len(missing) - 20))
    if failed:
        print("  ❌ 失败: %d" % len(failed))
        for r, e in failed:
            print("    %s : %s" % (r, e))

    print()
    print("  %s" % ("[DRY-RUN] 未实际修改" if dry else "[完成]"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

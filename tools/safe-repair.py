#!/usr/bin/env python3
"""安全修复 SD 卡文件：严格校验包版本 + 只覆盖真正损坏的真实文件

安全措施：
  1. **版本校验**：包版本必须与卡上 pacman 数据库记录完全一致，否则跳过
     （防止把"版本差异"误判为"损坏"而错误升级/降级）
  2. **跳过符号链接**：只处理真实文件，避免破坏 .so 链
  3. **备份**：被覆盖的文件保存为 .bad-<ts>
  4. **dry-run**：先看清单再执行

用法: safe-repair.py <包目录> <卡根> [--dry-run] [--skip-pkg A,B]
"""
import hashlib
import os
import re
import shutil
import sys
import tarfile
import time

SKIP_NAMES = (".PKGINFO", ".INSTALL", ".MTREE", ".BUILDINFO", ".Changelog")
SKIP_EXT = (".spdx", ".json", ".cmake", ".prl", ".h", ".pc", ".tmpfiles",
            ".conf", ".mo", ".gz")


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def pkg_name_ver(filename):
    """qt6-base-6.12.0-2-aarch64.pkg.tar.xz -> (qt6-base, 6.12.0-2)
    注意：版本可含 epoch 冒号（如 1:1.8.13-1），所以不能用 [^-] 简单切分。
    从右往左找最后一个 -<pkgrel>，并锚定在 -aarch64/-any 之前。
    """
    base = re.sub(r"\.pkg\.tar\.(xz|zst|gz)$", "", filename)
    base = re.sub(r"\.sig$", "", base)
    m = re.match(r"^(.*?)-([^/]*?-(?:aarch64|any))$", base)
    # base 形如 <name>-<version>-<pkgrel>-<arch>
    m = re.match(r"^(.*)-([0-9][^-]*)-([0-9]+)-(?:aarch64|any)$", base)
    if m:
        return m.group(1), m.group(2) + "-" + m.group(3)
    # 版本里可能还有别的情况，退化为按最后一个 '-' 切
    m = re.match(r"^(.*)-([0-9][^-]*)-(?:aarch64|any)$", base)
    if m:
        return m.group(1), m.group(2)
    return None, None


def norm_ver(v):
    """归一化版本号：解码 URL 编码的 epoch 冒号"""
    if v is None:
        return None
    return v.replace("%3A", ":").replace("%3a", ":")

# 自测
if __name__ == "__main__" and False:
    for t in ("qt6-base-6.12.0-2-aarch64.pkg.tar.xz",
              "iptables-1%3A1.8.13-1-aarch64.pkg.tar.xz",
              "libcap-2.78-1-aarch64.pkg.tar.xz",
              "opencode-2.0.27-1-aarch64.pkg.tar.xz"):
        print(t, "->", pkg_name_ver(t))


def installed_version(cardroot, pkgname):
    """从卡上 pacman 数据库读已安装版本

    稳健性要点（踩过的坑）：
      1. os.listdir 顺序不定 —— 必须排序，否则 libcap 会匹配到 libcap-ng
      2. 前缀匹配必须精确：目录名 == "<pkg>-<ver>-<rel>"，且 pkg 后紧跟 '-'
         且剩余部分以数字开头（版本号），避免 libcap 命中 libcap-ng
      3. desc 文件可能本身损坏（全空字节）—— 必须校验内容，失败则回退到目录名
    """
    base = os.path.join(cardroot, "var/lib/pacman/local")
    if not os.path.isdir(base):
        return None

    prefix = pkgname + "-"
    cands = []
    for d in sorted(os.listdir(base)):
        if not d.startswith(prefix):
            continue
        rest = d[len(prefix):]
        # rest 形如 "2.78-1" 或 "0.9.6-1"；必须以数字开头
        if not rest or not rest[0].isdigit():
            continue          # 排除 libcap-ng（rest="ng-0.9.6-1"）
        cands.append(d)

    for d in cands:
        # 优先从 desc 读（最准）
        desc = os.path.join(base, d, "desc")
        if os.path.isfile(desc):
            try:
                txt = open(desc, encoding="utf-8", errors="replace").read()
                m = re.search(r"%VERSION%\n([^\n]+)", txt)
                if m:
                    v = m.group(1).strip()
                    # 校验：必须是可打印 ASCII，且含数字
                    if v and v.isascii() and any(c.isdigit() for c in v) and len(v) < 80:
                        return v
            except OSError:
                pass
        # 回退：从目录名解析 <name>-<ver>-<rel>
        rest = d[len(prefix):]
        m = re.match(r"^(.+-[0-9]+)$", rest)
        if m:
            return m.group(1)
        return rest
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    pkgdir, cardroot = args[0], args[1]
    dry = "--dry-run" in sys.argv
    skip_pkgs = set()
    for a in sys.argv:
        if a.startswith("--skip-pkg"):
            i = sys.argv.index(a)
            if i + 1 < len(sys.argv):
                skip_pkgs = set(sys.argv[i + 1].split(","))

    staging = "/tmp/pt35-staging2"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    pkgs = sorted(f for f in os.listdir(pkgdir)
                  if ".pkg.tar" in f and not f.endswith(".sig"))

    print("── 包版本校验 ──")
    usable = []
    for p in pkgs:
        name, ver = pkg_name_ver(p)
        ver = norm_ver(ver)
        if not name:
            print("  [跳过] %-46s 无法解析包名" % p)
            continue
        if name in skip_pkgs:
            print("  [跳过] %-46s 按 --skip-pkg 要求" % p)
            continue
        inst = installed_version(cardroot, name)
        if inst is None:
            print("  [跳过] %-46s 卡上未安装" % p)
            continue
        # 比较：包版本 vs 已安装的 pkgver-pkgrel（忽略 epoch）
        inst_n = norm_ver(inst)
        if ver != inst_n:
            print("  [跳过] %-46s 版本不符 卡上=%s 包=%s" % (p, inst, ver))
            continue
        print("  [采用] %-46s 版本 %s ✓" % (p, ver))
        usable.append(p)

    print()
    print("── 解包 %d 个包 ──" % len(usable))
    nfiles = 0
    for p in usable:
        try:
            with tarfile.open(os.path.join(pkgdir, p), "r:*") as t:
                for m in t.getmembers():
                    base = os.path.basename(m.name)
                    if base in SKIP_NAMES or not m.isfile():
                        continue
                    t.extract(m, staging)
                    nfiles += 1
        except Exception as e:
            print("  [WARN] %s: %s" % (p, e))
    print("  提取 %d 个真实文件（已排除符号链接与元数据）" % nfiles)
    print()

    ts = time.strftime("%m%d-%H%M%S")
    fixed, ok, added, failed = [], 0, [], []

    for dp, dn, fns in os.walk(staging):
        for fn in fns:
            src = os.path.join(dp, fn)
            rel = os.path.relpath(src, staging)
            dst = os.path.join(cardroot, rel)

            # 卡上是符号链接 → 跳过（避免破坏 .so 链）
            if os.path.islink(dst):
                ok += 1
                continue
            if not os.path.exists(dst):
                added.append(rel)
                if not dry:
                    try:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                    except OSError as e:
                        failed.append((rel, str(e)))
                continue

            try:
                if os.path.getsize(src) == os.path.getsize(dst) and \
                   sha256(src) == sha256(dst):
                    ok += 1
                    continue
            except OSError as e:
                failed.append((rel, "读取失败: %s" % e))
                continue

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

    print("── 结果 ──")
    print("  已正确/跳过(链接): %d" % ok)
    print("  需修复:            %d" % len(fixed))
    for r in fixed:
        print("    FIX  %s" % r)
    if added:
        print("  卡上缺失(补齐):    %d" % len(added))
        for r in added[:10]:
            print("    ADD  %s" % r)
    if failed:
        print("  ❌ 失败 %d:" % len(failed))
        for r, e in failed:
            print("    %s : %s" % (r, e))
    print()
    print("  %s" % ("[DRY-RUN] 未修改任何文件" if dry else "[完成] 已修复"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

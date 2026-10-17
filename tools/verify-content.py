#!/usr/bin/env python3
"""verify-content.py —— 真正的内容校验（pacman -Qkk 查不出内容损坏）

背景
----
这台设备多次出现"文件大小正确、ELF 魔数正确、但内容被填成 0x00 或 0xFF"
的静默损坏（libLLVM / btop / qt6-base / xray-knife / p11-kit）。

`pacman -Qkk` **查不出来** —— 它的 mtree 只比大小/权限/时间戳，
不校验内容 SHA256。`ldd` 也查不出来，因为符号表还在。

本工具用**包缓存里的原版**逐个字节对比，是唯一可靠的方法。

用法
----
    sudo verify-content.py                 # 校验所有有缓存包的已装包
    sudo verify-content.py p11-kit glibc   # 只校验指定包
    sudo verify-content.py --list          # 列出哪些包有缓存可比对
    sudo verify-content.py --fix p11-kit   # 校验并自动修复

退出码
------
    0  全部一致
    1  发现内容不一致
    2  用法错误 / 无缓存包可比对
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

CACHE_DIR = Path("/var/cache/pacman/pkg")
CACHE_SUFFIXES = (".pkg.tar.xz", ".pkg.tar.zst", ".pkg.tar.gz", ".pkg.tar.bz2")
ARCHES = ("aarch64", "x86_64", "armv7h", "any", "arm", "i686")

# 用户有权修改的配置 —— 不该从包还原（否则会覆盖真实配置）
USER_EDITABLE = (
    "/etc/locale.gen", "/etc/locale.conf", "/etc/environment", "/etc/hostname",
    "/etc/hosts", "/etc/fstab", "/etc/crypttab", "/etc/resolv.conf",
    "/etc/nsswitch.conf", "/etc/man_db.conf", "/etc/pacman.conf",
    "/etc/mkinitcpio.conf", "/etc/ssh/sshd_config", "/etc/ssh/ssh_config",
    "/etc/systemd/journald.conf", "/etc/systemd/logind.conf",
    "/etc/NetworkManager/", "/etc/systemd/network/", "/etc/systemd/system/",
    "/etc/default/", "/etc/profile.d/", "/etc/sysctl.d/", "/etc/modprobe.d/",
    "/etc/udev/rules.d/", "/etc/X11/", "/etc/fonts/", "/etc/wpa_supplicant/",
    # 树莓派启动配置
    "/boot/config.txt", "/boot/cmdline.txt", "/boot/firmware/config.txt",
    "/boot/firmware/cmdline.txt",
)


def is_user_editable(path: str) -> bool:
    """这个文件是用户配置吗？（是则不该从包还原）"""
    if path in USER_EDITABLE:
        return True
    return any(path.startswith(p) for p in USER_EDITABLE if p.endswith("/"))

R = "\033[0m"; B = "\033[1;37m"; G = "\033[32m"; Y = "\033[33m"
RD = "\033[31m"; D = "\033[90m"


def ok(msg):   print(f"  {G}✓{R} {msg}")
def warn(msg): print(f"  {Y}!{R} {msg}")
def err(msg):  print(f"  {RD}✗{R} {msg}", file=sys.stderr)
def hdr(msg):  print(f"\n{B}{msg}{R}")


def _strip_suffix(name: str):
    """foo-1.2.3-4-aarch64.pkg.tar.zst → foo-1.2.3-4-aarch64"""
    for suf in CACHE_SUFFIXES:
        if name.endswith(suf):
            return name[: -len(suf)]
    return None


def _split_pkgfile(stem: str):
    """把缓存文件名拆成 (包名, 版本-发行号)。

    不能简单 split('-')：版本号里可能有 epoch 冒号
    （mesa-1:25.2.0-1-aarch64）、包名里可能有连字符
    （xorg-server-common-21.1.25-2-aarch64）。

    做法：先去掉架构后缀，再从**右往左**取两段作为版本-发行号，
    剩下的就是包名。
    """
    for arch in ARCHES:
        if stem.endswith("-" + arch):
            core = stem[: -(len(arch) + 1)]
            parts = core.rsplit("-", 2)
            if len(parts) == 3:
                return parts[0], f"{parts[1]}-{parts[2]}"
            break
    return None, None


def find_cache(pkg: str, version: str | None = None):
    """找到某个包的缓存归档（忽略 .sig）。"""
    cands = []
    for p in CACHE_DIR.iterdir():
        if p.name.endswith(".sig"):
            continue
        stem = _strip_suffix(p.name)
        if stem is None:
            continue
        name, ver = _split_pkgfile(stem)
        if name != pkg:
            continue
        cands.append((ver, p))
    if not cands:
        return None
    if version is not None:
        for ver, path in cands:
            if ver == version:
                return path
    # 退而求其次：取最新的
    return sorted(cands, key=lambda t: t[1].stat().st_mtime)[-1][1]


def installed_version(pkg: str):
    try:
        out = subprocess.run(["pacman", "-Q", pkg], capture_output=True,
                             text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.split()[1]
    except Exception:
        pass
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def malloc_like(path: Path):
    """检测连续 0x00 / 0xFF 填充 —— 这台设备的典型损坏特征。"""
    runs = {0x00: 0, 0xFF: 0}
    best = {0x00: 0, 0xFF: 0}
    try:
        with open(path, "rb") as f:
            prev, cur = None, 0
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                for byte in b:
                    if byte in runs:
                        if byte == prev:
                            cur += 1
                        else:
                            cur = 1
                        prev = byte
                        if cur > best[byte]:
                            best[byte] = cur
                    else:
                        prev, cur = None, 0
    except OSError:
        return None
    return best


def verify_pkg(pkg: str, fix: bool, deep: bool):
    """返回 (checked, bad_files)。"""
    inst_v = installed_version(pkg)
    if inst_v is None:
        return None

    cache = find_cache(pkg, inst_v)
    if cache is None:
        return None

    # 再次确认版本匹配（对比不同版本毫无意义）
    _, cver = _split_pkgfile(_strip_suffix(cache.name) or "")
    if cver != inst_v:
        warn(f"{pkg}: 缓存 {cver}，已装 {inst_v} —— 跳过（版本不一致）")
        return None

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            with tarfile.open(cache, "r:*") as tf:
                members = [m for m in tf.getmembers()
                           if m.isfile() and not m.name.startswith(".")]
                tf.extractall(tmp, members=members)
        except Exception as e:
            err(f"{pkg}: 解包失败 {e}")
            return None

        checked = 0
        user_edited = 0
        bad = []
        for m in members:
            rel = m.name
            src = tmp / rel
            dst = Path("/") / rel
            if not src.is_file() or not dst.is_file():
                continue
            checked += 1
            if is_user_editable("/" + rel):
                user_edited += 1
                continue
            if src.stat().st_size != dst.stat().st_size:
                bad.append((rel, "大小不符", None))
                continue
            if sha256(src) != sha256(dst):
                note = None
                if deep:
                    runs = malloc_like(dst)
                    if runs:
                        mx = max(runs.values())
                        if mx >= 512:
                            which = "0xFF" if runs[0xFF] > runs[0x00] else "0x00"
                            note = f"连续 {mx} 字节 {which}"
                bad.append((rel, "内容不一致", note))

        ue = f"  {D}({user_edited} 个配置跳过){R}" if user_edited else ""
        if not bad:
            print(f"  {G}✓{R} {pkg:<24} {checked:>5} 文件  一致{ue}")
        else:
            print(f"  {RD}✗{R} {pkg:<24} {checked:>5} 文件  "
                  f"{RD}{len(bad)} 个不一致{R}")
            for rel, reason, note in bad[:20]:
                extra = f"  ({note})" if note else ""
                print(f"      {RD}·{R} /{rel}  {D}{reason}{extra}{R}")
            if len(bad) > 20:
                print(f"      {D}… 还有 {len(bad)-20} 个{R}")

            if fix:
                hdr(f"修复 {pkg}")
                backup_dir = Path("/root/pt35-verify-backup") / pkg
                backup_dir.mkdir(parents=True, exist_ok=True)
                for rel, _, _ in bad:
                    src = tmp / rel
                    dst = Path("/") / rel
                    try:
                        shutil.copy2(dst, backup_dir / Path(rel).name)
                        shutil.copy2(src, dst)
                        os.chmod(dst, src.stat().st_mode & 0o7777)
                        ok(f"已还原 /{rel}")
                    except Exception as e:
                        err(f"还原 /{rel} 失败: {e}")
                subprocess.run(["ldconfig"], check=False)
                warn(f"原文件备份在 {backup_dir}")
        return checked, len(bad)


def main():
    ap = argparse.ArgumentParser(
        description="用包缓存逐字节校验已装文件（pacman -Qkk 查不出内容损坏）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("packages", nargs="*", help="要校验的包（默认全部有缓存的）")
    ap.add_argument("--fix", action="store_true", help="发现不一致时自动从缓存包还原")
    ap.add_argument("--list", action="store_true", help="只列出哪些包有缓存可比对")
    ap.add_argument("--deep", action="store_true",
                    help="额外检测连续 0x00/0xFF 填充（较慢）")
    args = ap.parse_args()

    if os.geteuid() != 0:
        err("需要 root（要读 /var/cache/pacman/pkg 和系统文件）")
        return 2

    if args.packages:
        pkgs = args.packages
    else:
        # 用 pacman 提供权威包名（别从文件名反推，epoch 会把它搞乱）
        try:
            out = subprocess.run(["pacman", "-Qq"], capture_output=True,
                                 text=True, timeout=60, check=True)
            allinst = [l.strip() for l in out.stdout.splitlines() if l.strip()]
        except Exception as e:
            err(f"无法获取已装包列表: {e}")
            return 2
        if not CACHE_DIR.is_dir():
            err(f"{CACHE_DIR} 不存在")
            return 2
        pkgs = [p for p in allinst if find_cache(p, installed_version(p))]

    if not pkgs:
        err(f"{CACHE_DIR} 里没有与已装版本匹配的缓存包")
        print("  提示: 先下载缓存 —— sudo pacman -Sw --needed $(pacman -Qq)")
        return 2

    if args.list:
        hdr(f"有缓存可比对的已装包（{len(pkgs)} 个）")
        for p in pkgs:
            v = installed_version(p)
            c = find_cache(p, v)
            cver = _split_pkgfile(_strip_suffix(c.name) or "")[1] if c else None
            match = f"{G}✅{R}" if (c and cver == v) else f"{Y}⚠️ 版本不一致{R}"
            print(f"  {p:<34} 已装 {str(v):<22} {match}")
        return 0

    hdr(f"逐字节校验 {len(pkgs)} 个包")
    print(f"  {D}（对比对象：{CACHE_DIR} 里的原始包）{R}")

    total_files = total_bad = skipped = 0
    bad_pkgs = []
    for p in pkgs:
        r = verify_pkg(p, args.fix, args.deep)
        if r is None:
            skipped += 1
            continue
        c, b = r
        total_files += c
        total_bad += b
        if b:
            bad_pkgs.append(p)

    hdr("汇总")
    print(f"  校验文件:   {total_files}")
    print(f"  内容不一致: {total_bad}")
    print(f"  跳过:       {skipped}（无缓存或版本不一致）")
    if total_bad:
        print(f"\n  {RD}发现 {len(bad_pkgs)} 个包有损坏文件:{R}")
        for p in bad_pkgs:
            print(f"    · {p}")
        print(f"\n  {Y}修复: sudo {sys.argv[0]} --fix {' '.join(bad_pkgs)}{R}")
        return 1
    print(f"\n  {G}✅ 全部一致 —— 未发现内容损坏{R}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

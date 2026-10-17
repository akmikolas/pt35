#!/usr/bin/env python3
"""从 Arch ARM 镜像下载指定包，提取文件用于修复损坏的系统文件

用法:
  repair-from-mirror.py <包名>=<损坏文件路径> [<包名>=<路径> ...]
  可选: --outdir DIR    提取目录（默认 /tmp/pt35fix）
        --repo core|extra  仓库（默认自动尝试 core 然后 extra）

例:
  repair-from-mirror.py zlib=usr/lib/libz.so.1.3.2 gdbm=usr/lib/libgdbm.so.6.0.0
"""
import os
import re
import sys
import tarfile
import urllib.request

MIRRORS = [
    "https://mirrors.ustc.edu.cn/archlinuxarm/aarch64/{repo}/",
    "https://mirrors.aliyun.com/archlinuxarm/aarch64/{repo}/",
]
ELF = b"\x7fELF"


def log(msg):
    print("  " + msg, flush=True)


def list_repo(base, timeout=40):
    req = urllib.request.Request(base, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def find_pkg(html, name):
    """在仓库目录列表里找 <name>-<ver>-aarch64.pkg.tar.xz，返回文件名（优先最新）"""
    pat = re.compile(r'href="(' + re.escape(name) + r'-[0-9][^"/]*?-aarch64\.pkg\.tar\.(?:xz|zst))"')
    hits = sorted(set(pat.findall(html)))
    return hits


def version_key(fn):
    """从文件名提取版本用于排序（粗略但够用）"""
    m = re.match(r".*?-([0-9][^-]*)-[0-9]+-aarch64", fn)
    return m.group(1) if m else fn


def download(url, dst, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dst, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return total


def main():
    args = sys.argv[1:]
    outdir = "/tmp/pt35fix"
    if "--outdir" in args:
        i = args.index("--outdir")
        outdir = args[i + 1]
        del args[i:i + 2]

    targets = []          # [(pkg, innerpath)]
    for a in args:
        if "=" not in a:
            log("跳过无效参数: %s" % a)
            continue
        pkg, path = a.split("=", 1)
        targets.append((pkg, path.lstrip("/")))

    if not targets:
        print(__doc__)
        return 2

    os.makedirs(outdir, exist_ok=True)
    ok_all = True

    for pkg, inner in targets:
        log("=" * 56)
        log("包 %s  →  需修复 %s" % (pkg, inner))

        pkgfile = None
        url = None
        for mirror in MIRRORS:
            for repo in ("core", "extra"):
                base = mirror.format(repo=repo)
                try:
                    html = list_repo(base)
                except Exception as e:
                    log("  仓库不可达 %s (%s): %s" % (repo, base.split("/")[2], e))
                    continue
                hits = find_pkg(html, pkg)
                if hits:
                    pkgfile = hits[-1]          # 取最后一个（通常最新）
                    url = base + pkgfile
                    log("  找到: %s (%s)" % (pkgfile, repo))
                    break
            if url:
                break

        if not url:
            log("  [FAIL] 所有镜像都没找到包 %s" % pkg)
            ok_all = False
            continue

        local = os.path.join(outdir, pkgfile)
        if not os.path.exists(local):
            try:
                n = download(url, local)
                log("  已下载 %.1f MB" % (n / 1024 / 1024))
            except Exception as e:
                log("  [FAIL] 下载失败: %s" % e)
                ok_all = False
                continue
        else:
            log("  已存在缓存: %s" % pkgfile)

        # 提取目标文件
        try:
            with tarfile.open(local, "r:*") as t:
                members = [m for m in t.getmembers()
                           if m.name.lstrip("./") == inner and m.isfile()]
                if not members:
                    # 放宽匹配
                    members = [m for m in t.getmembers()
                               if m.name.lstrip("./").endswith(inner) and m.isfile()]
                if not members:
                    log("  [FAIL] 包内找不到 %s" % inner)
                    ok_all = False
                    continue
                m = members[0]
                t.extract(m, outdir)
                extracted = os.path.join(outdir, m.name)
                with open(extracted, "rb") as f:
                    head = f.read(4)
                good = head == ELF
                log("  提取: %s (%d 字节) %s" % (m.name, m.size,
                                                "ELF-OK" if good else "非ELF!"))
                if not good:
                    ok_all = False
        except Exception as e:
            log("  [FAIL] 解包失败: %s" % e)
            ok_all = False

    log("=" * 56)
    log("提取目录: %s" % outdir)
    log("结果: %s" % ("✅ 全部就绪" if ok_all else "❌ 有失败项"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

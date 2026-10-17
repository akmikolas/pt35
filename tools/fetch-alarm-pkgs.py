#!/usr/bin/env python3
"""批量下载 Arch Linux ARM 包到笔记本（用于离线修复 SD 卡）

用法: fetch-alarm-pkgs.py <输出目录> <包名> [包名...]
"""
import os
import re
import sys
import urllib.request

MIRRORS = [
    "https://mirrors.ustc.edu.cn/archlinuxarm/aarch64/{repo}/",
    "http://os.archlinuxarm.org/aarch64/{repo}/",
    "https://mirrors.aliyun.com/archlinuxarm/aarch64/{repo}/",
]


def fetch(url, timeout=60, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data


def list_repo(base):
    try:
        return fetch(base, timeout=45).decode("utf-8", "replace")
    except Exception:
        return ""


def pkg_pattern(name):
    # 处理 epoch：文件名里冒号被编码为 %3A；也匹配不带 epoch 的
    n = re.escape(name)
    return re.compile(r'href="(' + n + r'-[0-9][^"/]*?-aarch64\.pkg\.tar\.(?:xz|zst))"')


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    outdir = sys.argv[1]
    names = sys.argv[2:]
    os.makedirs(outdir, exist_ok=True)

    ok, fail = [], []
    for name in names:
        found = None
        for mirror in MIRRORS:
            for repo in ("core", "extra", "alarm"):
                base = mirror.format(repo=repo)
                html = list_repo(base)
                if not html:
                    continue
                hits = sorted(set(pkg_pattern(name).findall(html)))
                if hits:
                    found = (base, hits[-1], repo)
                    break
            if found:
                break

        if not found:
            print("  [FAIL] %-20s 所有镜像都未找到" % name)
            fail.append(name)
            continue

        base, fn, repo = found
        dst = os.path.join(outdir, fn.replace("%3A", ":"))
        if os.path.exists(dst) and os.path.getsize(dst) > 1000:
            print("  [SKIP] %-20s 已存在 %s" % (name, fn))
            ok.append(name)
            continue
        try:
            data = fetch(base + fn, timeout=300)
            with open(dst, "wb") as f:
                f.write(data)
            print("  [OK]   %-20s %s (%.1f MB, %s)"
                  % (name, fn, len(data) / 1024 / 1024, repo))
            ok.append(name)
        except Exception as e:
            print("  [FAIL] %-20s 下载失败: %s" % (name, e))
            fail.append(name)

    print()
    print("  成功 %d / 失败 %d" % (len(ok), len(fail)))
    if fail:
        print("  失败列表: " + " ".join(fail))
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())

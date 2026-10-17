#!/usr/bin/env python3
"""精确检测系统库损坏：区分【符号链接】/【GNU ld 链接脚本】/【真损坏】

误报来源（上一版踩过）：
  1. 符号链接 —— os.walk 会列出，open() 会跟随，读到的是目标内容
  2. GNU ld 链接脚本 —— .so 常是指向 libX.so.1 的文本脚本，开头是 "/* GNU ld script"
正常 ELF 的标志：前 4 字节 == b"\\x7fELF"
"""
import os
import subprocess
import sys

ELF = b"\x7fELF"
SCRIPT_MARKERS = (b"/* GNU ld script", b"GROUP (", b"INPUT (", b"OUTPUT_FORMAT")


def classify(path):
    """返回 (状态, 说明)"""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError as e:
        return "error", f"读取失败: {e}"

    if head[:4] == ELF:
        return "ok", ""
    # 文本链接脚本
    if any(m in head for m in SCRIPT_MARKERS):
        return "script", ""
    # 其它文本（可能是脚本的变体）
    if head[:1] in (b"#", b"/") and all(32 <= b < 127 or b in (9, 10, 13) for b in head[:32]):
        return "textish", head[:32].decode("ascii", "replace").strip()
    # 剩余：真损坏
    kind = "全零" if head[:8] == b"\x00" * 8 else head[:8].hex()
    return "corrupt", kind


def main():
    roots = [p for p in sys.argv[1:] if os.path.isdir(p)] or ["/usr/lib", "/lib"]
    counts = {"ok": 0, "script": 0, "textish": 0, "corrupt": 0, "error": 0, "link": 0}
    bad = []
    seen = set()

    for root in roots:
        for dp, dn, fns in os.walk(root, followlinks=False):
            for fn in fns:
                p = os.path.join(dp, fn)
                rp = os.path.realpath(p)
                if rp in seen:          # 同一实体只查一次
                    continue
                seen.add(rp)
                if os.path.islink(p):   # 符号链接本身不判内容
                    counts["link"] += 1
                    continue
                if ".so" not in fn:     # 只看库文件
                    continue
                st, info = classify(p)
                counts[st] += 1
                if st in ("corrupt", "error"):
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = -1
                    bad.append((p, st, info, size))

    print("  扫描统计（去重后实体）:")
    print(f"    正常 ELF:      {counts['ok']}")
    print(f"    链接脚本:      {counts['script']}  ← 正常，非损坏")
    print(f"    其它文本:      {counts['textish']}")
    print(f"    符号链接:      {counts['link']}  ← 跳过")
    print()
    if bad:
        print(f"  ❌❌ 真正损坏: {len(bad)} 个")
        for p, st, info, size in bad:
            print(f"    {p}  [{st}] size={size} head={info}")
    else:
        print("  ✅ 未发现真正损坏的库")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

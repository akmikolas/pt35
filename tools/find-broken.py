#!/usr/bin/env python3
"""全系统损坏文件扫描 + 归属包映射（不依赖 sed/file/pacman 等受损工具）

原理：直接读 /var/lib/pacman/local/<pkg>/files 获取每个包的文件清单，
      再逐个校验二进制/库文件是否为合法 ELF 或文本脚本。
"""
import os
import sys

ELF = b"\x7fELF"
TEXT_OK = (b"/* GNU ld script", b"GROUP (", b"INPUT (", b"#!", b"#!/")
# 这些扩展名/路径不需要是 ELF
SKIP_EXT = (".conf", ".socket", ".service", ".target", ".timer", ".mount",
            ".txt", ".md", ".json", ".xml", ".desktop", ".pc", ".h", ".py",
            ".sh", ".pl", ".vim", ".rules", ".list", ".preset", ".path",
            ".slice", ".scope", ".device", ".swap", ".automount", ".netdev",
            ".network", ".link", ".nspawn", ".tmpfile", ".journal")


def looks_binary(path):
    """只关心应该是 ELF 的文件：在 bin/sbin 下，或 .so 结尾，或无扩展名"""
    base = os.path.basename(path)
    if base.endswith(SKIP_EXT):
        return False
    if "/bin/" in path or "/sbin/" in path:
        return True
    if ".so" in base:
        return True
    if "." not in base:          # 无扩展名的可执行文件
        return True
    return False


def check(path):
    try:
        if os.path.islink(path):
            return "link", ""
        if not os.path.isfile(path):
            return "skip", ""
        st = os.stat(path)
        if not (st.st_mode & 0o111) and ".so" not in os.path.basename(path):
            return "skip", ""
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError as e:
        return "error", str(e)

    if head[:4] == ELF:
        return "ok", ""
    for m in TEXT_OK:
        if m in head:
            return "text", ""
    # 纯 ASCII 文本行（配置类）
    if all(32 <= b < 127 or b in (9, 10, 13) for b in head[:48]):
        return "text", ""
    return "corrupt", head[:8].hex()


def pacman_owner_map():
    """从 pacman 本地数据库读每个包拥有的文件"""
    owner = {}
    localdb = "/var/lib/pacman/local"
    if not os.path.isdir(localdb):
        return owner
    for entry in os.listdir(localdb):
        fp = os.path.join(localdb, entry, "files")
        if not os.path.isfile(fp):
            continue
        pkg = entry.rsplit("-", 2)[0]
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.startswith("%") and line.startswith("/"):
                        owner.setdefault(line, []).append(pkg)
        except OSError:
            pass
    return owner


def main():
    roots = ["/usr/bin", "/usr/sbin", "/usr/lib", "/bin", "/sbin"]
    corrupt = []
    stats = {"ok": 0, "text": 0, "link": 0, "skip": 0, "corrupt": 0, "error": 0}
    seen = set()

    for root in roots:
        if not os.path.isdir(root):
            continue
        for dp, dn, fns in os.walk(root, followlinks=False):
            for fn in fns:
                p = os.path.join(dp, fn)
                rp = os.path.realpath(p)
                if rp in seen:
                    continue
                seen.add(rp)
                if not looks_binary(p):
                    continue
                st, info = check(p)
                stats[st] = stats.get(st, 0) + 1
                if st == "corrupt":
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = -1
                    corrupt.append((p, size, info))

    print("  扫描统计: " + "  ".join(f"{k}={v}" for k, v in stats.items() if v))
    print()
    if not corrupt:
        print("  ✅ 未发现损坏的二进制/库")
        return 0

    print(f"  ❌ 损坏文件 {len(corrupt)} 个：")
    owner = pacman_owner_map()
    pkgs = {}
    for p, size, head in corrupt:
        who = owner.get(p, ["?"])
        print(f"    {p}  size={size} head={head}  包={','.join(who)}")
        for w in who:
            pkgs[w] = pkgs.get(w, 0) + 1
    print()
    print("  需要重装的包：")
    for k, v in sorted(pkgs.items(), key=lambda x: -x[1]):
        print(f"    {k}  ({v} 个文件)")
    print()
    print("  一键修复命令：")
    print("    pacman -S --noconfirm " + " ".join(sorted(pkgs)))
    return 1


if __name__ == "__main__":
    sys.exit(main())

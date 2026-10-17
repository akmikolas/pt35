#!/usr/bin/env python3
"""检查 PSF 控制台字体的 Unicode 表覆盖情况（判断 TUI 制表符能否正常显示）"""
import gzip
import struct
import sys

BOX = [ord(c) for c in "─│┌┐└┘├┤┬┴┼━┃┏┓┗┛╔╗╚╝═║╭╮╰╯█▀▄▌▐░▒▓•·←→↑↓…✓⚠"]


def probe(path):
    try:
        raw = open(path, "rb").read()
    except OSError:
        return "  %s: 不存在" % path
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    if len(raw) < 5:
        return "  %s: 文件过短" % path

    magic = struct.unpack_from("<H", raw, 0)[0]
    mode, charsize, glyph = raw[2], raw[3], raw[4]
    has_uni = bool(charsize & 1)
    is512 = bool(mode & 1)
    nchars = 512 if is512 else 256

    present = [chr(cp) for cp in BOX if struct.pack("<H", cp) in raw]
    missing = [chr(cp) for cp in BOX if struct.pack("<H", cp) not in raw]

    lines = [
        "  %s" % path.split("/")[-1],
        "    magic=0x%04x  字符数=%d  字形高=%d  Unicode表=%s"
        % (magic, nchars, glyph, "有" if has_uni else "无"),
        "    覆盖制表符/符号 %d/%d" % (len(present), len(BOX)),
    ]
    if present:
        lines.append("      有: " + "".join(present))
    if missing:
        lines.append("      缺: " + "".join(missing))
    return "\n".join(lines)


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "/usr/share/kbd/consolefonts/Lat2-Terminus16.psfu.gz",
        "/usr/share/kbd/consolefonts/ter-u16n.psf.gz",
        "/usr/share/kbd/consolefonts/default8x16.psfu.gz",
    ]
    for t in targets:
        print(probe(t))
        print()

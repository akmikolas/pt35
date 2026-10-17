# Findings

Write-ups from building this on real hardware. Each one records **how the problem was
found**, not just the fix — the diagnostic path is usually the reusable part.

| # | Document | Core finding |
|---|---|---|
| 01 | [系统优化与排障](01-系统优化与排障.md) | WiFi/触摸/键盘联调；`libinput` 设备顺序 |
| 02 | [轻量系统与代理选型](02-轻量系统与代理选型.md) | 为什么选 Arch 而非 Ubuntu Server；命令行代理方案对比 |
| 03 | [图形界面无法加载](03-图形界面无法加载.md) | `libvulkan` 损坏 → sway 起不来 |
| 04 | [系统库损坏与离线恢复](04-系统库损坏与离线恢复.md) | 从 SD 卡离线提取软件包修复；两个脚本自杀陷阱 |
| 05 | [正确关机方式](05-正确关机方式.md) | `halt` ≠ 断电；官方关机流程 |
| 06 | [SD卡损坏的识别与定位](06-SD卡损坏的识别与定位.md) | ⭐ **`ldd` 查不出内容损坏**，只有校验和能 |
| 07 | [开机动画设计](07-开机动画设计.md) | ⭐ **块字符是双宽的**；终端尺寸不能靠字号推算 |
| 08 | [系统深挖与Bug修复](08-系统深挖与Bug修复.md) | ⭐ **`/run/user/$UID` 会随会话销毁**；getty 抢 tty1；restart 竞态 |
| 09 | [xray-knife](09-xray-knife.md) | 代理工具链用法（凭据随机生成的坑） |

## If you only read three

1. **[07](07-开机动画设计.md)** — if you write any TUI, the double-width block character
   trap will bite you, and the failure is silent.
2. **[06](06-SD卡损坏的识别与定位.md)** — unclean shutdowns produce files that pass
   `ldd`, load fine, and then abort. Only a checksum catches them.
3. **[08](08-系统深挖与Bug修复.md)** — three systemd/lifetime issues that each look like
   "the desktop randomly died".

## Redaction

All documents were written during real debugging sessions. Credentials, subscription
URLs, hostnames and addresses have been replaced with placeholders. Substitute your own.
The technical content is unchanged.

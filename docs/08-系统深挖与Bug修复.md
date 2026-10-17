# 2026-10-16 系统深挖：发现的 Bug 与修复

> **Note on redaction.** This document was written while debugging a real device.
> All credentials, subscription URLs, hostnames and addresses have been replaced
> with placeholders (`192.168.1.100`, `MyWiFi`, `user@device`, `YOUR_PASSWORD`).
> Substitute your own values. The technical content is unchanged.

---


> 本轮目标：深挖隐患，保证日常使用不出问题。共发现 **6 个真实 Bug**，
> 其中 3 个会导致**开机后桌面不可用**。

---

## 🔴 Bug 1：`libLLVM.so.23.1` 损坏 → sway 崩溃、桌面起不来

**症状**：开机后桌面进程没起来，`pt35-desktop` 状态 `failed`。

**错误信息**（极具误导性）：
```
LLVM ERROR: out of memory
Allocation failed
Aborted (core dumped)   ← sway 退出码 134 = SIGABRT

backtrace:
  eglQueryString            (libEGL.so.1)
  wlr_egl_create_with_drm_fd
  wlr_gles2_renderer_create_with_drm_fd
  (libwlroots-0.20.so) → sway
```

**误导点**：报的是 "out of memory"，但实际内存 **3287 MB 空闲**。

**真正的定位方法**：
```bash
$ pacman -Qkk llvm-libs
llvm-libs: /usr/lib/libLLVM.so.23.1 (SHA256 checksum mismatch)
llvm-libs: 16 total files, 1 altered file     ← 找到了
```

**修复**：
```bash
pacman -Sw --noconfirm --nodeps llvm-libs      # 只下载
PKG=$(ls -t /var/cache/pacman/pkg/llvm-libs-*.pkg.tar.* | grep -v .sig | head -1)
pacman -U --noconfirm "$PKG"                   # 只装这一个包
```
修复后 SHA256：`44517c29…` → `a6280228…`，`0 altered files`。

> **这是本机第 N 次 SD 卡内容损坏**。特征永远是：
> **文件大小正确、`ldd` 正常、但内容错误** —— 只有校验和或实际执行才能发现。
> `ldd` 查不出这种损坏！

---

## 🔴 Bug 2：`getty@tty1` 把桌面踢掉

**症状**：桌面启动成功（日志有"中文桌面运行中"），但 45 秒后被停掉。

**时间线**：
```
17:21:19  Started Getty on tty1.                    ← getty 启动
17:22:04  Stopping Getty on tty1...
17:22:04  Stopping PocketTerm35 中文桌面...          ← 桌面被连带停掉
17:22:04  pt35-desktop: Main process exited, status=143（SIGTERM）
```

**根因**：
```
getty@tty1 → WantedBy=getty.target → multi-user.target → graphical.target
→ 每次开机必然启动
pt35-desktop 的 Conflicts=kmsconvt@tty1.service（tty1 归桌面管）
→ systemd 启动 getty@tty1 时，因 tty1 冲突停掉 pt35-desktop
```

**修复**：**永久屏蔽**（软链到 /dev/null，任何依赖都拉不起来）
```bash
systemctl mask getty@tty1.service
```
> 注意：`disable` 不够 —— getty.target 仍会拉起它。必须 `mask`。

---

## 🔴 Bug 3：`/run/user/0` 被会话生命周期销毁 → wayland socket 消失

**症状**：桌面进程还活着，但 `grim`/`foot` 报
`failed to connect to wayland; no compositor running?`

**证据**：
```
16:58:42 Starting User Runtime Directory /run/user/0...
16:59:40 Stopping User Runtime Directory /run/user/0...   ← 我 SSH 断开
16:59:44 Starting User Runtime Directory /run/user/0...   ← 目录被重建（空的！）
```
`/run/user/0` 的 inode 一直在变，而 sway 的 wayland socket 就在里面。

**根因**：root 未开 lingering（`LINGER: no`），systemd-logind 在**最后一个会话结束时**
销毁并重建 `/run/user/0`。

**修复**：运行时目录搬到 `/run/pt35`（与登录会话无关）
```ini
[Service]
RuntimeDirectory=pt35
RuntimeDirectoryMode=0700
Environment=XDG_RUNTIME_DIR=/run/pt35
```
并改 `zhdesk`：
```bash
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/pt35}"   # 尊重外部传入
```

**验证**：断开 SSH → 重连 → socket 仍在（inode 未变）→ 截图成功。

---

## 🟡 Bug 4：`pt35-firstboot` 卡 45 分钟 + 永久失败

**症状**：`pt35-firstboot.service` 状态 `failed`，且每次开机重试。

**日志**：
```
16:00:12 pacman: Starting full system upgrade...
16:00:27 pacman: [67B blob data]
16:45:21 pacman: looking for conflicting packages...
16:45:21 pacman: :: raspberrypi-overlays-20260611-2 and linux-rpi-6.18.55-1 are in conflict. Remove linux-rpi? [y/N]
16:45:21 error: unresolvable package conflicts detected
```
**在交互提示上卡了 45 分钟**（`TimeoutStartSec=infinity`）。

**为什么危险**：
```ini
ExecStart=/usr/bin/pacman -Syu --noconfirm --needed raspberrypi-overlays
ConditionPathExists=!/var/lib/pt35-firstboot.done
```
① `pacman -Syu` 会**全系统升级** —— 正是导致 `linux-rpi` 冲突的原因
② 缺 `--noconfirm` → 卡交互提示
③ `TimeoutStartSec=infinity` → 永不超时
④ 标记文件不存在 → **每次开机都重试**，可能持有 `db.lck`

**修复**：
```bash
systemctl disable pt35-firstboot.service
touch /var/lib/pt35-firstboot.done     # 补上标记，双保险
```
> `linux-rpi` 已装、`/boot/overlays/` 有 390 个文件、dtoverlay 正常工作
> → 这个服务的使命已完成，禁用无副作用。

---

## 🟡 Bug 5：`pt35-motd` 慢到卡终端（2349 ms → 245 ms）

**症状**：每次开终端 / SSH 登录都卡 2.3 秒。

**根因链**：
| 阶段 | 耗时 | 原因 |
|---|---|---|
| 初版 | **2349 ms** | `vlen()` 对**每个字符**调 `_dw()` 子shell → 上千次 fork |
| 修 1 | 405 ms | 一次性剥离 ANSI + ASCII 快速路径 + 结果缓存 |
| 修 2 | **245 ms** | `_rep` 缓存 + 仪表条缓存（`${var//}` 是逐字符替换，78 字符跑 78 次 printf）|

**最终结构**：
```bash
declare -A _VLEN_CACHE=() _REP_CACHE=() _BAR_CACHE=()
vlen() {                       # 显示宽度（不是字符数！）
    local s=$1 out='' rest
    while [[ $s == *$'\033['* ]]; do   # 纯 bash 剥离 ANSI
        out+="${s%%$'\033['*}"; rest="${s#*$'\033['}"; s="${rest#*m}"
    done
    s="$out$s"
    local hit=${_VLEN_CACHE[$s]:-}; [ -n "$hit" ] && { printf '%s' "$hit"; return; }
    [[ $s != *[$'\x80'-$'\xff']* ]] && { _VLEN_CACHE[$s]=${#s}; printf '%d' ${#s}; return; }
    # 含 CJK：逐字符，双宽 +2
}
```

**踩到的坑**：
- 用 `sed 's/[0-9;]*m//g'` 剥 ANSI 会**误删正常内容**（如 `100m`）→ 必须用 ESC 前缀匹配
- `${#s}` 是**字符数**不是**显示宽度** → 中文要 +2，否则带中文的行超宽折行

---

## 🟡 Bug 6：`systemctl restart pt35-desktop` 有竞态 → 桌面起不来

**症状**：`restart` 后桌面 `failed`（`Result=timeout`），而 `start` 正常。

**日志**：
```
17:48:31 Started PocketTerm35 中文桌面...
17:48:31 Stopping PocketTerm35 中文桌面...      ← 同一秒又 stop
17:48:41 State 'stop-sigterm' timed out. Killing.
17:48:41 Killing process (zhdesk) with signal SIGKILL
```

**根因**：`zhdesk` 末尾是 `wait "$SWAY_PID"`，systemd 的 `restart`
在**同一秒**内 start+stop，新实例与旧实例抢 seat/DRM。
即使把 `TimeoutStopSec` 从 10s 提到 35s **也无效**（不是超时不够，是竞态）。

**规避**：新增 `pt35-desktop-restart`（走 stop → 等干净 → start）
```bash
pt35-desktop-restart
```
**也可直接重启整机**（最稳）。

---

## 📊 全量校验结果（`pacman -Qkk`，1800+ 包）

| 包 | 差异数 | 类型 | 判定 |
|---|---|---|---|
| `llvm-libs` | 1 | **SHA256** | 🔴 **已修**（导致 sway 崩溃）|
| `btop` | 1 | **SHA256** | 🔴 **已修**（强制重装）|
| `qt6-base` | 222 | SHA256 | 🟡 已修唯一的运行时库 `libQt6DBus` |
| `glib2` | 10 | SHA256 | ⚪ 只坏翻译文件（`.mo`），库本身 OK |
| `noto-fonts-cjk` | 3 | SHA256 | ⚪ 80 个中文字体可用，渲染正常 |
| `linux-firmware-*` | 16 | SHA256 | ⚪ 高通/Intel/NVIDIA 网卡固件，本机用不到 |
| `linux-rpi` | 417 | **Modification time** | ✅ 正常（内核升级后 mtime 变化）|
| `raspberrypi-bootloader` | 17 | **Modification time** | ✅ 正常 |
| `/etc/*`（10 个）| — | backup file | ✅ 我有意修改的，都有备份 |
| `gettext`/`kbd`/`linux-api-headers` | — | mtree gzip 损坏 | ⚪ 仅 pacman 元数据 |

**qt6-base 详情**：222 个里 **213 个在 `/usr/include`**（C++ 头文件，运行时无关），
只有 `libQt6DBus.so.6.12.0` 是运行时库 —— 已单独从包里提取替换
（`6827bc51…` → `1934eedb…`）。**没有重装整个 qt6-base**（避免连锁风险）。

---

## ✅ 新增/更新的工具

| 命令 | 用途 |
|---|---|
| `pt35-motd` | 控制共振风格欢迎页（245ms，17 行 × 78 列）|
| `pt35-proxy` | 代理一站式管理（状态/测试/更新/重启）|
| `pt35-desktop-restart` | 安全重启桌面（绕开 systemd restart 竞态）|
| `pt35-healthcheck` | 新增**图形栈 + getty + XDG_RUNTIME_DIR** 三项检查 |

**healthcheck 新增检查**（都是本轮踩坑后加的）：
```bash
libLLVM.so.23.1          ✅   # 损坏会导致 sway "out of memory" 崩溃
libQt6DBus.so.6.12.0     ✅
libEGL / libgbm / libwlroots ✅
getty@tty1               ✅ (masked)   # 非 masked 会踢掉桌面
XDG_RUNTIME_DIR=/run/pt35 ✅          # 用 /run/user/0 会随 SSH 断开被删
```

---

## 🎓 本轮核心教训

1. **`ldd` 查不出内容损坏** —— 必须用 SHA256（`pacman -Qkk`）或实际执行。
   `libLLVM` 损坏时 `ldd` 完全正常。
2. **错误信息会骗人** —— "LLVM ERROR: out of memory" 实际是文件损坏，内存有 3GB 空闲。
3. **`disable` ≠ `mask`** —— getty@tty1 被 getty.target 拉起，只有 `mask` 能挡住。
4. **tmpfs 会随会话消失** —— `/run/user/0` 在 SSH 断开时被销毁，关键 socket 要放 `/run/<service>`。
5. **性能要测量，不要猜** —— MOTD 慢的真正原因是**逐字符 fork**，不是 I/O。
6. **`${#var}` 是字符数**，不是终端显示宽度；CJK 是双宽。

---

## 📋 日常使用建议

```bash
# 开机后想确认一切正常
pt35-healthcheck          # 快速检查（含新增的图形栈检查）
pt35                      # 看所有命令

# 桌面相关
pt35-desktop-restart      # ★ 需要重启桌面时用这个（不要用 systemctl restart）
# 或者直接重启整机

# 代理
pt35-proxy                # 状态一览
pt35-proxy run <命令>     # 单命令走代理
# 详细文档: /root/XRAY-KNIFE.md

# 关机（务必用这个，等绿灯停再双击顶部键）
pt35-poweroff
```

**如果哪天桌面又起不来**，按顺序排查：
```bash
pt35-healthcheck                                    # ① 图形栈 + getty + runtime dir
pacman -Qkk llvm-libs qt6-base glib2 2>&1 | grep -i "sha256\|altered"   # ② 库损坏
tail -30 /tmp/zhdesk.log                           # ③ 桌面日志
journalctl -u pt35-desktop -b | tail -30           # ④ 服务日志
pt35-desktop-restart                               # ⑤ 安全重启
```

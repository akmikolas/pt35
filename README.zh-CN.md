# pt35 —— PocketTerm35 Linux 定制

[English](README.md) · **中文**

> 掌上树莓派终端：极简中文桌面、CRT 风格开机动画，以及一套**发现并修复 SD 卡文件系统损坏**的工具链。

在 **微雪 PocketTerm35**（树莓派 4B，aarch64，Arch Linux ARM）上实测部署。
仓库里所有内容都在真机上跑过 —— **包括踩过的坑**。

---

## 这是什么

一台跑 Arch Linux ARM 的掌上 Pi 终端，包含：

- **极简中文桌面** —— sway + foot + fcitx5，无面板无壁纸，内存占用约 50 MB。
  kmscon 留在 tty1 作为救援终端，桌面占用 tty2。
- **CRT 故障风开机动画** —— 《控制：共振》视觉语言的 ASCII 动画
  （粗野主义碑体、单一高饱和红、周期性信号丢失），
  进度由**真实 systemd 服务状态**驱动，不是假进度条。
- **零 fork 的欢迎页** —— 17 行 × 78 列的机构终端风格 MOTD，
  在 Pi 4B 上 **245 ms** 渲染完成。
- **修复工具链** —— 这台设备因非正常关机**损坏过 7 次文件系统**。
  这里的工具能查出 `fsck` 和 `ldd` 都发现不了的损坏。

全部 16 个命令共用一套元数据驱动的帮助系统：

```bash
pt35                 # 按分类列出所有命令
pt35-help wifi       # 详细用法（从脚本自身提取）
pt35 <TAB>           # bash 补全
man pt35-help        # man 手册
```

---

## 截图

| 开机动画 | 欢迎页 |
|---|---|
| ![boot](assets/boot-progression.png) | ![motd](assets/motd-foot.png) |

完整动画：[`assets/control-resonance.gif`](assets/control-resonance.gif) ·
故障版：[`assets/control-tv-glitch.gif`](assets/control-tv-glitch.gif)

---

## 目录结构

```
bin/       16 个命令（都带 `# help:` 元数据）
systemd/   单元文件（含两个真实竞态的修复）
config/    foot.ini、sway 配置、fcitx5 profile、pt35.conf.example
tools/     文件系统损坏检测与修复（Python，仅标准库）
docs/      8 篇记录 —— 重点是"发现过程"，不只是配方
assets/    截图
```

---

## 安装

```bash
git clone <this-repo> pt35 && cd pt35
sudo ./install.sh --dry-run     # 先看会做什么
sudo ./install.sh               # 执行
```

`install.sh` 幂等、覆盖前会备份；非 aarch64 或缺少硬件时会拒绝运行
（除非加 `--force`）。

---

## 三个最值得一看的发现

这三条花的时间最多，而且适用于**任何** Linux 终端 UI 项目 —— 不只是这个硬件。

### 1. 块字符是双宽的

`█ ▓ ▒ ░ ▄ ▀` **不在** DejaVu Sans Mono 里。终端会回退到 CJK 字体，
在那里它们渲染成 **2 个字符位**。真机实测：

| 内容 | 字符数 | 实测像素 | 字符位 |
|---|---|---|---|
| `▓` × 10 | 10 | 108 | **13.4** |
| `▄` × 10 | 10 | 197 | **24.6** |
| `X` × 20 | 20 | 160 | **20.0** ✅ |

所有列宽计算会**静默失效**。需要对齐的地方**只用纯 ASCII**。
→ [`docs/07-开机动画设计.md`](docs/07-开机动画设计.md)

### 2. `ldd` 查不出库文件损坏

非正常关机丢失脏页后，文件会变成**大小正确、ELF 头合法、但内容错误**。
`ldd` 会成功，二进制能加载，然后崩溃：

```
LLVM ERROR: out of memory      ← 报的是内存不足
Allocation failed                 但当时有 3.2 GB 空闲
Aborted (core dumped)          ← sway 渲染器初始化
```

唯一可靠的检测手段是**校验和**：

```bash
pacman -Qkk llvm-libs
# llvm-libs: /usr/lib/libLLVM.so.23.1 (SHA256 checksum mismatch)
```
→ [`docs/06-SD卡损坏的识别与定位.md`](docs/06-SD卡损坏的识别与定位.md)

### 3. `/run/user/$UID` 会随最后一个会话结束而销毁

Wayland 合成器的 socket 放在 `$XDG_RUNTIME_DIR`。当 root 没开 lingering
且你断开最后一个 SSH 会话时，systemd 会**销毁并重建** `/run/user/0`：

```
16:59:40 Stopping User Runtime Directory /run/user/0...
16:59:44 Starting User Runtime Directory /run/user/0...   ← 重建，是空的
```

合成器还在跑，但所有客户端都连不上了。解决办法是搬走：

```ini
[Service]
RuntimeDirectory=pt35
Environment=XDG_RUNTIME_DIR=/run/pt35
```
→ [`docs/08-系统深挖与Bug修复.md`](docs/08-系统深挖与Bug修复.md)

---

## 其它已记录的坑

| 现象 | 原因 | 位置 |
|---|---|---|
| 桌面起来了，约 45 秒后挂掉 | `getty@tty1` 抢了 tty1，`Conflicts=` 把桌面停掉。`disable` 不够，必须 `mask` | [docs/08](docs/08-系统深挖与Bug修复.md) |
| `systemctl restart <桌面>` 之后起不来 | start 和 stop 落在同一秒；合成器的 `wait` 阻塞超过 `TimeoutStopSec` | [docs/08](docs/08-系统深挖与Bug修复.md) |
| 终端 UI 画一次要 2.3 秒 | 宽度函数里逐字符 `$(...)` —— 上千次 fork。加缓存 + 纯 bash 剥离 → 245 ms | [docs/07](docs/07-开机动画设计.md) |
| `fc-list "字体:charset=..."` 结果不可信 | 它匹配的是**字体族**不是具体文件。要看字形必须渲染后读回 framebuffer | [docs/07](docs/07-开机动画设计.md) |
| SSH 认证成功但立刻断开 | `libkrb5` 损坏 → sshd 里 `SIGILL` | [docs/04](docs/04-系统库损坏与离线恢复.md) |
| 触摸能用但打字不行（或反过来） | 驱动变动后 `libinput` 设备顺序变了 | [docs/01](docs/01-系统优化与排障.md) |

---

## 配置

复制模板再改：

```bash
sudo install -m644 config/pt35.conf.example /etc/pt35.conf
```

```ini
STATIC_IP=192.168.1.100/24
STATIC_GW=192.168.1.1
FAN_GPIO=14
TEMP_WARN=55
```

本仓库**不含**任何真实凭据、主机名或地址。
`./check-secrets.sh` 会强制这一点 —— 提交前跑一次。

---

## 硬件说明

- **显示**：HDMI→DPI 640×480。foot 用 `DejaVu Sans Mono:size=11` 时是 **80×24**
  （**不要**从字号推算，用 `tput` 实测）。
- **风扇**：GPIO14 **没有硬件 PWM**，用 `pwm-gpio-fan` 走软件 PWM。
- **键盘**：RP2040 跑 CircuitPython，通过 USB OTG 接入。改键在 Linux 侧
  用 evdev/uinput 做 —— 因为原厂 `boot.py` 禁用了 USB 存储，
  没法直接改 `code.py`。
- **Pi 4B 没有 PCIe** —— M.2 存储只能走 USB。

---

## 许可

MIT —— 见 [LICENSE](LICENSE)。

厂商资料（微雪原理图、3D 模型、设备树 overlay）**不在**仓库里；
链接见 [`docs/`](docs/)。第三方社区项目只放链接，不 vendor。

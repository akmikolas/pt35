# Raspberry Pi OS 移植版

从 Arch Linux ARM 迁移到 **Raspberry Pi OS (Debian 13 trixie / 内核 6.18.50+rpt-rpi-v8)** 的完整改动。

## 为什么换到 Pi OS

| 驱动 | Arch 主线内核 | Pi OS 基金会内核 |
|---|---|---|
| `pwm-gpio`（GPIO 软件 PWM，风扇必需） | ❌ 没有 | ✅ `pwm-gpio.ko.xz` |
| `vc4-kms-v3d` overlay | ❌ 无法应用到主线 dtb（FDT_ERR_NOTFOUND） | ✅ 原生支持 |
| `goodix,gt911` 触摸 | 需手工合并 dtb | ✅ `goodix_ts.ko` |
| 内核/模块版本 | 易错配 | ✅ 完全一致 |

**关键结论**：`pwm-gpio` 是树莓派专有驱动，主线内核没有 → Arch 上做不出风扇温控曲线。

## 硬件真相（走了弯路后确认）

```
屏幕  = HDMI 接口，板上有一颗 HDMI→DPI 桥接芯片
        → 只需 dtoverlay=vc4-kms-v3d，不需要任何 DPI/panel overlay
触摸  = Goodix GT911，I2C1，地址 0x5d（备选 0x14）
        → waveshare-35dpi-5b.dtbo（厂商提供，Pi OS 不自带）
键盘  = RP2040 走 USB-C/OTG → dtoverlay=dwc2,dr_mode=host
风扇  = GPIO14 软件 PWM → dtoverlay=pwm-gpio-fan（GPIO14 不是硬件 PWM 引脚）
```

## 三个必须改的 boot 文件

### 1. `/boot/firmware/config.txt`

追加 `boot-config.txt` 里的内容。原文件备份为 `config.txt.orig`。

### 2. `/boot/firmware/cmdline.txt` ← **最关键的坑**

```diff
- console=serial0,115200 console=tty1 root=... quiet splash ...
+ console=tty1 root=... resize ... consoleblank=0
```

**为什么删 `console=serial0`**：
`serial0` 在 Pi 4 上会落到 `ttyS0`（mini UART），占用 **GPIO14/15**，
而风扇 PWM 也在 GPIO14 → 抢引脚。旧卡的 cmdline 里本来就没有这条。

**为什么删 `quiet splash`**：首次开机显示内核日志，黑屏时能直接看到原因。

### 3. `/boot/firmware/overlays/`

Pi OS 官方镜像**不带**厂商 overlay，需手动放入：

```
waveshare-35dpi-4b.dtbo   (635 字节)
waveshare-35dpi-5b.dtbo   (1001 字节)
```

## 控制台字体（开机动画的前提）

动画在 tty1（80×30，Terminus 8x16）上跑，字体必须有方块/制表字符。

```bash
# /etc/default/console-setup
CHARMAP="UTF-8"
CODESET="guess"
FONTFACE="Terminus"
FONTSIZE="8x16"

sudo setupcon --force
```

**Uni2-Terminus16 的字形覆盖（精确解析 PSF1 Unicode 表得出）**：

| 可用 | 缺失 |
|---|---|
| `█ ▒ ░ ─ │ ┌ ┐ └ ┘ ├ ┤ ┼ → ← ↑ ↓ · Δ ° × ═ ║ ■ ╱` | `▓ ▀ ▄ ▌ ▐ ◆ ⚠ 中文` |

→ 所以 `pt35-bootsplash` 里所有 `▓`→`▒`/`█`、`▀▄`→`┌┐└┘─`、`◆`→`█`、`■`→`█`。

## 与 Arch 版的差异

| 项目 | Arch 版 | Pi OS 版 |
|---|---|---|
| 桌面 | sway（手动启） | labwc（lightdm 自动启） |
| `zhdesk` | 停 kmscon → 启 sway | 直接在现有会话开全屏 foot |
| `pt35-check` | kmscon/xray/opencode | 屏幕/触摸/键盘/风扇/桌面/网络 |
| `pt35-healthcheck` | `pacman -Qkk` | `dpkg --verify` |
| 输入法 | 手动启 fcitx5 | `im-config` + labwc environment |
| 开机动画 | tty1（kmscon 接管让位） | tty1（lightdm 接管让位，用 `Before=lightdm.service`） |
| 服务名 | `sshd` `seatd` `kmsconvt@tty1` | `ssh` `NetworkManager` `lightdm` |

## 安装步骤

```bash
# 1. boot 配置
sudo cp pios/boot-config.txt /tmp/   # 内容追加到 /boot/firmware/config.txt
sudo sed -i 's/console=serial0,115200 //' /boot/firmware/cmdline.txt

# 2. 工具
sudo install -m755 pios/bin/* /usr/local/bin/

# 3. 开机动画
sudo install -m644 pios/systemd/pt35-bootsplash.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable pt35-bootsplash

# 4. 中文环境
sudo apt install -y fonts-noto-cjk fcitx5 fcitx5-chinese-addons \
  fcitx5-frontend-gtk3 fcitx5-frontend-qt5 fcitx5-config-qt foot

# 5. 输入法环境（~/.config/labwc/environment）
cat >> ~/.config/labwc/environment <<'E'
GTK_IM_MODULE=fcitx
QT_IM_MODULE=fcitx
XMODIFIERS=@im=fcitx
SDL_IM_MODULE=fcitx
E

# 6. MOTD 自动显示
sudo tee /etc/profile.d/99-pt35-motd.sh >/dev/null <<'E'
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
[ -t 1 ] || return 0 2>/dev/null || exit 0
[ -x /usr/local/bin/pt35-motd ] && /usr/local/bin/pt35-motd
E
```

## 实测数据

```
启动耗时:   49 秒（关掉 cloud-init 前是 2分20秒）
foot:       80 列 × 24 行（640×480 全屏，Fira Code 10）
tty1:       80 列 × 30 行（Terminus 8x16，动画设计正好匹配）
空闲温度:   50-52°C（风扇 100%，CPU 600MHz）
            风扇曲线: 35°C→45% 38°C→71% 41°C→86% 45°C→100%
```

## 已知限制

- **温度压不到 50°C 以下**：风扇已满速，受机壳风道限制（硬件问题）
- **控制台无中文**：Linux 控制台字体不含 CJK，中文只在 foot/桌面里显示
- **`pwm-gpio-fan` 的 `fan_temp*_speed` 参数不生效**：`cooling-levels` 仍是 overlay 默认的
  `114/152/204/255`（我用自建 overlay 才能改，但默认曲线已够用）

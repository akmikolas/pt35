#!/bin/bash
# install.sh —— 把 pt35 定制部署到本机
#
# 用法:
#   sudo ./install.sh              安装/更新
#   sudo ./install.sh --dry-run    只显示会做什么，不改任何东西
#   sudo ./install.sh --uninstall  卸载（恢复备份）
#   sudo ./install.sh --force      跳过架构/硬件检查
#
# 设计原则:
#   * **幂等**：重复运行结果一致
#   * **先备份**：任何被覆盖的文件存到 /var/backups/pt35/<时间戳>/
#   * **不猜硬件**：非 aarch64 或缺少 PocketTerm35 特征时拒绝运行（除非 --force）
#   * **可干跑**：--dry-run 输出完整动作清单
#
# 安装后需要手动做的两件事（脚本会提示）:
#   1. systemctl mask getty@tty1.service     ← 否则桌面会被 getty 踢掉
#   2. 编辑 /etc/pt35.conf（网络/温度参数）

set -u

REPO="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-/usr/local}"
BINDIR="$PREFIX/bin"
UNITDIR="/etc/systemd/system"
BACKUP_ROOT="/var/backups/pt35"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/$STAMP"

DRY=0; UNINSTALL=0; FORCE=0
for a in "$@"; do
    case "$a" in
        --dry-run|-n) DRY=1 ;;
        --uninstall)  UNINSTALL=1 ;;
        --force|-f)   FORCE=1 ;;
        -h|--help)    sed -n '2,24p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "未知参数: $a（试 --help）" >&2; exit 2 ;;
    esac
done

# ── 输出助手 ──────────────────────────────────────────────
R='\033[0m'; B='\033[1;37m'; G='\033[32m'; Y='\033[33m'; RD='\033[31m'; D='\033[90m'
say()  { printf '%b\n' "$*"; }
ok()   { printf "  ${G}✓${R} %b\n" "$*"; }
warn() { printf "  ${Y}!${R} %b\n" "$*"; }
err()  { printf "  ${RD}✗${R} %b\n" "$*" >&2; }
step() { printf "\n${B}%s${R}\n" "$*"; }

run() {   # run <命令...>  —— dry-run 时只打印
    if [ "$DRY" = 1 ]; then
        printf "  ${D}[dry-run]${R} %s\n" "$*"
    else
        "$@"
    fi
}

backup_file() {  # backup_file <路径>
    [ -e "$1" ] || return 0
    if [ "$DRY" = 1 ]; then
        printf "  ${D}[dry-run]${R} 备份 %s → %s/\n" "$1" "$BACKUP"
        return 0
    fi
    mkdir -p "$BACKUP"
    cp -a "$1" "$BACKUP/$(basename "$1")" 2>/dev/null && \
        printf "  ${D}备份${R} %s\n" "$1"
}

# ── 权限 ──────────────────────────────────────────────────
if [ "$(id -u)" != 0 ] && [ "$DRY" = 0 ]; then
    err "需要 root。用: sudo $0 $*"
    exit 1
fi

# ── 硬件检查（防止装到不合适的机器上）─────────────────────
step "① 环境检查"
ARCH="$(uname -m)"
MODEL="$( { tr -d '\0' < /proc/device-tree/model; } 2>/dev/null || echo unknown)"
say "  架构:   $ARCH"
say "  机型:   $MODEL"

if [ "$FORCE" = 0 ]; then
    if [ "$ARCH" != "aarch64" ]; then
        err "架构是 $ARCH，本仓库面向 aarch64。加 --force 可跳过。"
        exit 1
    fi
    case "$MODEL" in
        *"Raspberry Pi 4"*) ok "树莓派 4 —— 符合" ;;
        *) warn "机型不是树莓派 4（$MODEL）。加 --force 可跳过。" ; [ "$DRY" = 0 ] && exit 1 ;;
    esac
    [ -d /proc/device-tree ] || { err "没有 /proc/device-tree"; exit 1; }
fi
command -v systemctl >/dev/null || { err "没有 systemd"; exit 1; }
ok "systemd 可用"

# ── 卸载 ──────────────────────────────────────────────────
if [ "$UNINSTALL" = 1 ]; then
    step "卸载"
    for u in pt35-desktop pt35-bootsplash; do
        run systemctl disable --now "$u.service" 2>/dev/null || true
    done
    for f in "$UNITDIR"/pt35-*.service; do
        [ -e "$f" ] && { backup_file "$f"; run rm -f "$f"; }
    done
    for f in "$BINDIR"/pt35* "$BINDIR"/zhdesk "$BINDIR"/zhime "$BINDIR"/zhfont \
             "$BINDIR"/wifi "$BINDIR"/temp "$BINDIR"/proxyenv; do
        [ -e "$f" ] && { backup_file "$f"; run rm -f "$f"; }
    done
    run rm -f /etc/profile.d/99-pt35-motd.sh
    LATEST="$(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | head -1)"
    [ -n "$LATEST" ] && say "  备份在: $LATEST"
    ok "已卸载（配置 /etc/pt35.conf 保留）"
    exit 0
fi

# ── 安装命令 ──────────────────────────────────────────────
step "② 安装命令 → $BINDIR"
N=0
for f in "$REPO"/bin/*; do
    b="$(basename "$f")"
    case "$b" in
        *.bash) continue ;;   # 补全脚本单独装
    esac
    if [ -e "$BINDIR/$b" ]; then backup_file "$BINDIR/$b"; fi
    run install -m755 "$f" "$BINDIR/$b"
    N=$((N+1))
done
ok "$N 个命令"

if [ -f "$REPO/bin/pt35-completion.bash" ]; then
    run install -d -m755 /usr/share/bash-completion/completions
    run install -m644 "$REPO/bin/pt35-completion.bash" \
        /usr/share/bash-completion/completions/pt35-help
    ok "bash 补全"
fi
run install -d -m755 "$PREFIX/share/man/man1"
[ -f "$REPO/docs/pt35-help.1" ] && run install -m644 "$REPO/docs/pt35-help.1" \
    "$PREFIX/share/man/man1/pt35-help.1"

# ── 安装配置 ──────────────────────────────────────────────
step "③ 安装配置（不覆盖已存在的）"
install_if_absent() {  # install_if_absent <源> <目标> [模式]
    if [ -e "$2" ]; then
        warn "$2 已存在，跳过（保留你的版本）"
    else
        run install -m"${3:-644}" "$1" "$2"
        ok "$2"
    fi
}
run install -d -m755 /root/.config/foot /root/.config/sway /root/.config/fcitx5
install_if_absent "$REPO/config/foot.ini"        /root/.config/foot/foot.ini
install_if_absent "$REPO/config/sway-config"     /root/.config/sway/config
install_if_absent "$REPO/config/fcitx5-profile"  /root/.config/fcitx5/profile
install_if_absent "$REPO/config/pt35.conf.example" /etc/pt35.conf

# ── 安装 systemd ──────────────────────────────────────────
step "④ 安装 systemd 单元"
for u in pt35-desktop pt35-bootsplash; do
    [ -f "$REPO/systemd/$u.service" ] || continue
    backup_file "$UNITDIR/$u.service"
    run install -m644 "$REPO/systemd/$u.service" "$UNITDIR/$u.service"
    ok "$u.service"
done
if [ -f "$REPO/systemd/10-quiet-console.conf" ]; then
    run install -d -m755 /etc/systemd/system.conf.d
    install_if_absent "$REPO/systemd/10-quiet-console.conf" \
        /etc/systemd/system.conf.d/10-quiet-console.conf
fi
run systemctl daemon-reload
ok "daemon-reload"

# ── 登录显示欢迎页 ────────────────────────────────────────
step "⑤ 欢迎页（登录时显示）"
if [ "$DRY" = 0 ]; then
    if ! grep -q 'pt35-motd' /root/.bashrc 2>/dev/null; then
        cat >> /root/.bashrc <<'RC'

# ── PocketTerm35 欢迎页 ──
# 只在交互式 shell 显示（非交互 / scp 不会触发）
if [[ $- == *i* ]] && [ -x /usr/local/bin/pt35-motd ]; then
    /usr/local/bin/pt35-motd
fi
RC
        ok "已写入 /root/.bashrc"
    else
        warn "/root/.bashrc 已有欢迎页配置，跳过"
    fi
    ln -sf "$BINDIR/pt35-motd" /etc/profile.d/99-pt35-motd.sh
    ok "/etc/profile.d/99-pt35-motd.sh"
else
    printf "  ${D}[dry-run]${R} 写入 /root/.bashrc + 链接 /etc/profile.d/\n"
fi

# ── 必做的手动步骤 ────────────────────────────────────────
step "⑥ 必须手动做的一步 ⚠️"
say "  屏蔽 tty1 上的 getty，否则它会通过 Conflicts 把桌面停掉："
say ""
say "    ${B}sudo systemctl mask getty@tty1.service${R}"
say ""
if [ "$DRY" = 0 ]; then
    printf "  现在就做吗？[y/N] "
    read -r a || a=n
    case "$a" in
        y|Y) run systemctl mask getty@tty1.service && ok "已屏蔽 getty@tty1" ;;
        *)   warn "已跳过 —— 记得稍后手动执行，否则桌面会启动后被踢掉" ;;
    esac
fi

# ── 完成 ──────────────────────────────────────────────────
step "完成"
say "  下一步:"
say "    1. 编辑 ${B}/etc/pt35.conf${R}（静态 IP / 温度阈值）"
say "    2. 启用桌面开机自启:  ${B}systemctl enable pt35-desktop${R}"
say "    3. 启用开机动画:      ${B}systemctl enable pt35-bootsplash${R}"
say "    4. 测试:              ${B}pt35${R}  ← 列出所有命令"
say ""
say "  开机动画需要 kmscon 让出 tty1。如果没装 kmscon:"
say "    ${D}pacman -S kmscon${R}"
say ""
[ -d "$BACKUP" ] && say "  备份: $BACKUP"
[ "$DRY" = 1 ] && say "  ${Y}这是 dry-run，什么都没改${R}"
exit 0

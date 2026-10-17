#!/bin/bash
# check-secrets.sh —— 提交前机密自检
#
# 用法:
#   ./check-secrets.sh              扫工作区
#   ./check-secrets.sh --staged     只扫 git 暂存区（pre-commit 用）
#   ./check-secrets.sh --history    扫全部 git 历史（发布前跑一次）
#
# 退出码: 0=干净  1=发现可疑内容
#
# 设计说明：
#   本仓库是真实设备的配置特化，天然会碰到"像密码的东西"。
#   所以规则分两级：
#     🔴 BLOCK  —— 明确是凭据/私人信息，必须修
#     🟡 WARN   —— 可能是，人工确认
#   并把已知的【占位符/示例值】列入白名单，避免误报。

set -u
MODE="${1:-work}"
FAIL=0

R='\033[0m'; RED='\033[1;31m'; YEL='\033[33m'; GRN='\033[32m'; DIM='\033[90m'; BOLD='\033[1;37m'

# ── 🔴 必须阻止的模式 ──────────────────────────────────────
BLOCK=(
    # 真实密钥格式
    'sk-[A-Za-z0-9]{24,}'                       # OpenAI/兼容 API key
    'ghp_[A-Za-z0-9]{30,}'                      # GitHub PAT
    'gho_[A-Za-z0-9]{30,}'
    'github_pat_[A-Za-z0-9_]{30,}'
    'xox[baprs]-[A-Za-z0-9-]{10,}'              # Slack
    'AKIA[0-9A-Z]{16}'                          # AWS
    'BEGIN [A-Z ]*PRIVATE KEY'                  # 私钥
    # 硬编码口令（排除明显的占位符）
    'password[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"']{6,}'
    'passwd[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"']{6,}'
    'SSHPASS=[^$"'"'"'{]'
    'psk=[0-9a-f]{16,}'
    # 订阅 / 代理凭据
    'sub\.[a-z0-9-]+\.(top|com|xyz|net)/sub/'
    'proxy-user[[:space:]]+[a-z0-9]+:[A-Za-z0-9]{8,}'
    # 真实内网 IP（允许 192.168.1.x 占位与标准保留段）
    '192\.168\.(0|2[0-9]|3[0-9]|4[0-9]|5[0-9]|6[0-9]|7[0-9]|8[0-9]|9[0-9]|[1-9][0-9]{2,})\.[0-9]+'
    '10\.(?!0\.0\.)[0-9]+\.[0-9]+\.[0-9]+'
    # 设备唯一标识
    '([0-9a-f]{2}:){5}[0-9a-f]{2}'
    # 私人路径
    '/home/(?!user|frank/Documents/code/pt35)[a-z]+/'
    '/Users/[a-z]+/'
)

# ── 🟡 需要人工确认 ────────────────────────────────────────
WARN=(
    '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'   # 任何 IP
    '(ssid|SSID)[[:space:]]*=[[:space:]]*[^ ]+'         # SSID
    'token[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"']+'
    'secret[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"']+'
)

# ── ⚪ 白名单：出现在这些上下文里就不算问题 ────────────────
#   （标准保留地址段、占位符、示例值）
ALLOW='192\.168\.1\.(1|100|101|102)|192\.168\.0\.0|10\.0\.0\.[0-9]|127\.0\.0\.1|0\.0\.0\.0|100\.64\.0\.[0-9]+|aa:bb:cc:dd:ee:[0-9a-f]{2}|YOUR_|EXAMPLE|example\.com|PLACEHOLDER|REDACTED|XXXX|192\.168\.1\.x|192\.168\.1\.1/24|223\.5\.5\.5|1\.1\.1\.1'

scan() {   # scan <模式数组名> <等级> <文件列表命令>
    local -n pats=$1
    local level=$2
    local -a files=()
    case "$MODE" in
        staged)  mapfile -t files < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null) ;;
        history) mapfile -t files < <(git log --all --pretty=format: --name-only 2>/dev/null | sort -u | grep -v '^$') ;;
        *)       mapfile -t files < <(git ls-files 2>/dev/null; find . -type f -not -path './.git/*' -not -path './assets/*' 2>/dev/null) ;;
    esac
    [ ${#files[@]} -eq 0 ] && return

    for pat in "${pats[@]}"; do
        local hits
        hits=$(printf '%s\0' "${files[@]}" | sort -zu | \
               xargs -0 -r grep -InE -- "$pat" 2>/dev/null | \
               grep -vE "$ALLOW" | grep -v "check-secrets.sh" | head -8)
        if [ -n "$hits" ]; then
            if [ "$level" = BLOCK ]; then
                printf "${RED}🔴 BLOCK${R} 模式 ${DIM}%s${R}\n" "$pat"
                printf '%s\n' "$hits" | sed 's/^/     /'
                FAIL=1
            else
                printf "${YEL}🟡 WARN ${R} 模式 ${DIM}%s${R}\n" "$pat"
                printf '%s\n' "$hits" | head -3 | sed 's/^/     /'
            fi
        fi
    done
}

printf "${BOLD}机密自检${R}  ${DIM}(模式: %s)${R}\n\n" "$MODE"
scan BLOCK BLOCK
scan WARN  WARN

if [ "$FAIL" = 0 ]; then
    printf "\n${GRN}✅ 未发现阻断级问题${R}\n"
    printf "${DIM}  提示: 🟡 项请人工确认；发布前跑 ./check-secrets.sh --history${R}\n"
else
    printf "\n${RED}❌ 发现阻断级问题，请修复后再提交${R}\n"
    printf "${DIM}  修复建议: 换成占位符（YOUR_PASSWORD / 192.168.1.100 / aa:bb:cc:dd:ee:ff）${R}\n"
fi
exit $FAIL

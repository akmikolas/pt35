# PocketTerm35 自定义命令的 bash 补全
# 安装位置: /usr/share/bash-completion/completions/pt35-help
#           /etc/bash_completion.d/pt35

# 收集所有 PocketTerm35 自定义命令
_pt35_commands() {
    local f
    for f in /usr/local/bin/*; do
        [ -x "$f" ] || continue
        local n=$(basename "$f")
        case "$n" in
            pt35-*|zhdesk|zhime|zhfont|wifi|temp|proxyenv) echo "$n" ;;
        esac
    done
}

# pt35-help 的补全：第一个参数补命令名
_pt35_help() {
    local cur prev
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$(_pt35_commands) --all --raw" -- "$cur") )
    fi
    return 0
}
complete -F _pt35_help pt35-help

# 有子命令的命令：补子命令
_pt35_desktop_boot() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "on off test status disable" -- "$cur") )
    fi
}
complete -F _pt35_desktop_boot pt35-desktop-boot

_pt35_zhime() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "zh en toggle status" -- "$cur") )
    fi
}
complete -F _pt35_zhime zhime

_pt35_zhfont() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "8 9 10 11 12 13 14 16 --list --restart" -- "$cur") )
    fi
}
complete -F _pt35_zhfont zhfont

_pt35_wifi() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "list status saved static dhcp forget" -- "$cur") )
    fi
}
complete -F _pt35_wifi wifi

_pt35_healthcheck() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    COMPREPLY=( $(compgen -W "--full" -- "$cur") )
}
complete -F _pt35_healthcheck pt35-healthcheck

# 快捷别名：pt35 <Tab> 也能列出所有命令
_pt35_alias() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    COMPREPLY=( $(compgen -W "$(_pt35_commands)" -- "$cur") )
}
complete -F _pt35_alias pt35

# pt35 <命令> 等价于直接执行该命令
pt35() {
    if [ $# -eq 0 ]; then
        pt35-help
    elif command -v "$1" >/dev/null 2>&1; then
        local c="$1"; shift; "$c" "$@"
    else
        pt35-help "$@"
    fi
}

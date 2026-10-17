# xray-knife 使用手册（PocketTerm35 实机版）

> **Note on redaction.** This document was written while debugging a real device.
> All credentials, subscription URLs, hostnames and addresses have been replaced
> with placeholders (`192.168.1.100`, `MyWiFi`, `user@device`, `YOUR_PASSWORD`).
> Substitute your own values. The technical content is unchanged.

---


> **本机实测环境**：Arch Linux ARM / aarch64 / Raspberry Pi 4B / 内核 6.18.55-1-rpi
> **xray-knife 版本**：11.4.0（静态 aarch64 二进制，62.7 MB）
> **文档日期**：2026-10-16
> **快速入口**：日常用 `pt35-proxy`（见 §2），深度操作用 `xray-knife` 原生命令（见 §4）

---

## 1. 一句话理解

`xray-knife` = xray-core/sing-box 的"瑞士军刀"。本机的用法是：

```
订阅 URL  ──subs fetch──▶  节点数据库(SQLite)
                              │
                              ├─ http 测速 ──▶  valid.txt（按延迟排序的可用节点）
                              │
                              └─ proxy inbound ──▶  本地 SOCKS5 127.0.0.1:9999
                                                     （每 600 秒自动轮换节点）
```

---

## 2. 日常使用：`pt35-proxy`（推荐）

```bash
pt35-proxy              # 看状态：服务/端口/凭据/当前节点/出口IP/延迟
pt35-proxy test         # 只测连通性
pt35-proxy on           # 打印如何在此 shell 开启代理
pt35-proxy run <命令>   # 在代理下执行一条命令（不动当前环境）
pt35-proxy update       # 拉取订阅更新节点
pt35-proxy nodes        # 列出节点池与订阅
pt35-proxy retest       # 重新测速全部节点，重排 valid.txt
pt35-proxy restart      # 重启代理服务
pt35-proxy log          # 尾随日志
```

**实测输出**：
```
xray-knife 代理状态
  服务      active  (enabled=enabled)
  版本      xray-knife 11.4.0
  监听      127.0.0.1:9999
  凭据      y4uay9pTVjCfuzKf:cnBSfl…  （每次重启随机）
  当前节点  vless://***@jp.node1.example.com:8088
  轮换      Next rotation in 10m0s
  节点池    8 个可用

  出口 IP   23.151.104.42  Google  204 ✅  延迟  0.437408s
```

### 在当前 shell 开启代理

```bash
source /usr/local/bin/proxyenv
# 输出: 代理已开启: socks5h://127.0.0.1:9999 (出口随节点自动轮换)

# 之后所有支持 http_proxy/https_proxy 的程序自动走代理
curl https://ifconfig.me

# 关闭
unset ALL_PROXY http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY
```

### 只给某条命令挂代理（推荐，不影响环境）

```bash
pt35-proxy run curl https://ifconfig.me
pt35-proxy run git clone https://github.com/xxx/yyy
pt35-proxy run pacman -Sy
```

---

## 3. ★ 重要：凭据是**随机的**

| 项 | 说明 |
|---|---|
| **SOCKS 地址** | `127.0.0.1:9999`（固定） |
| **用户名/密码** | **每次服务启动随机生成**，写入 `/run/xray-knife-proxy.env` |
| **为什么随机** | `xray-knife proxy inbound` 的默认行为（防未授权访问） |
| **重启后会变** | 是。所以**不要写死在脚本里** |

**正确做法**：
```bash
# ✅ 读文件
. /run/xray-knife-proxy.env
curl --socks5-hostname 127.0.0.1:9999 \
     --proxy-user "$XRAY_SOCKS_USER:$XRAY_SOCKS_PASS" https://example.com

# ✅ 或者直接用 pt35-proxy（已封装）
pt35-proxy run curl https://example.com

# ❌ 不要硬编码
curl --proxy-user user:REDACTED ...   # 这是 /etc/xray-knife/socks-credentials
                                              # 里的旧值，服务实际不用它
```

---

## 4. 原生 xray-knife 命令

### 4.1 全局参数

```bash
xray-knife --db <路径>     # 指定数据库（默认 ~/.xray-knife/xray-knife.db）
xray-knife --quiet         # 只输出警告和错误（数据行不受影响）
xray-knife -V              # 版本
```

### 4.2 `subs` —— 订阅管理

```bash
xray-knife subs add --url "https://example.com/sub" --remark "My VPN"
xray-knife subs show                      # 列出所有订阅
xray-knife subs fetch --all               # 拉取全部订阅的节点
xray-knife subs fetch --sub-id 1          # 只拉某个订阅
xray-knife subs list-configs --sub-id 1   # 列出该订阅拉到的节点
```

**本机现状**：
| 项 | 值 |
|---|---|
| 订阅 ID | `1` |
| URL | `https://sub.example.com/sub/YOUR_TOKEN…` |
| 备注 | `pasarguard` |
| 启用 | 是 |
| 上次拉取 | `2026-10-12 17:41:48` |
| 拉到的节点 | 5 个（数据库 `subscription_configs`） |

> ⚠️ `subs fetch` 会**同时写 configs.txt**（在 xray-knife 目录）。

### 4.3 `http` —— 测速与可用性

```bash
xray-knife http -f configs.txt            # 测文件里的节点 → valid.txt（按延迟排序）
xray-knife http --from-db                 # 测数据库里的节点
xray-knife http list-results              # 看上次测试结果
```

**常用参数**：
| 参数 | 说明 |
|---|---|
| `--amount uint` | 上下载测试量 KB（默认 10000） |
| `--speedtest-timeout` | 超时窗口，超出按已传输量计 |
| `--bind string` | 绑定出口网卡（Linux 需要 CAP_NET_RAW） |

> **本机现状**：`/root/valid.txt` 有 **8 个节点**。
> 注意数据库里订阅只有 5 个节点，valid.txt 有 8 个 —— 说明**曾经手动加过节点**。

### 4.4 `proxy` —— 运行代理（本机正在用的）

四种模式：
| 模式 | 说明 | 本机适用性 |
|---|---|---|
| `inbound` | 本地监听（最常用） | ✅ **本机用这个** |
| `system` | 本地监听 + 注册为系统代理 | 可用 |
| `app` | 每进程独立网络命名空间（`--shell`/`--namespace`） | 可用，需 root |
| `tun` | 主机级 TUN 捕获（Linux） | ⚠️ **SSH 下危险**，会截断自己的连接 |

```bash
# 本机实际使用的命令（在 /usr/local/lib/xray-knife-run.sh 里）
xray-knife proxy inbound \
    -f /root/valid.txt \
    --port 9999 \
    --inbound socks \
    --rotate 600 \        # 每 600 秒换节点
    --health-check 30     # 每 30 秒健康检查

# 清理崩溃残留（kill switch / namespace / 系统代理 / TUN 规则）
xray-knife proxy restore
```

### 4.5 其它命令

| 命令 | 用途 |
|---|---|
| `parse` | 解码分享链接，打印各字段；`--json` 输出完整 xray-core 配置 |
| `db` | 数据库维护：`backup` / `prune` / `migrate` / `stats` / `vacuum` |
| `net tcp` | 测到节点主机的 TCP 连接延迟 |
| `exec` | 进入已存在的代理命名空间执行命令 |
| `cfscanner` | 扫描 Cloudflare 优选 IP（支持断点续扫） |
| `webui` | 起本地 Web 界面管理一切 |
| `dpi` | 找能绕过 DPI 的分片/SNI 设置 |

**示例**：
```bash
xray-knife parse "vless://..."                    # 看节点详情
xray-knife parse -i --json < link.txt > out.json  # 转成 xray-core JSON
xray-knife db backup                              # 备份数据库
xray-knife net tcp -f valid.txt                   # 测 TCP 延迟
```

---

## 5. 文件与目录清单（本机实际路径）

| 路径 | 用途 | 权限 |
|---|---|---|
| `/usr/local/bin/xray-knife` | 二进制（62,652,540 字节） | 755 |
| `/usr/local/lib/xray-knife-run.sh` | 服务启动脚本 | 755 |
| `/etc/systemd/system/xray-knife-proxy.service` | systemd 单元 | 644 |
| `/etc/systemd/system/xray-knife-proxy.service.d/10-wait-network.conf` | 开机竞态修复覆盖 | 644 |
| `/run/xray-knife-proxy.env` | **本次随机凭据** | 644 |
| `/run/xray-knife-proxy.log` | 运行日志（含当前节点、轮换倒计时） | — |
| `/root/valid.txt` | 可用节点池（按延迟排序） | 644 |
| `/root/.xray-knife/xray-knife.db` | SQLite 数据库 | 600 |
| `/etc/xray-knife/socks-credentials` | 旧固定凭据（**服务不用**） | 600 |
| `/root/xray-knife.bad-1016-001453` | 损坏二进制的备份（可删） | — |

**二进制校验**：
```
SHA256: af48951ec9e187acbb28211551532cad4fd25001a181e4fee2d2481792feef09
```

### 数据库表结构

```sql
subscriptions           -- 订阅链接（id, url, remark, user_agent, enabled, last_fetched_at, created_at）
subscription_configs    -- 订阅拉到的节点（id, subscription_id, config_link, protocol, remark, added_at, last_seen_at）
subscription_config_sources
http_test_runs          -- 测速批次
http_test_results       -- 单节点测速结果
http_latest_results     -- 最新结果快照
cf_scan_results         -- Cloudflare 扫描结果
schema_migrations
```

**常用查询**：
```bash
DB=/root/.xray-knife/xray-knife.db
sqlite3 -header -column "$DB" "SELECT * FROM subscriptions;"
sqlite3 "$DB" "SELECT COUNT(*) FROM subscription_configs;"
sqlite3 -header -column "$DB" "SELECT remark, protocol FROM subscription_configs;"
sqlite3 -header -column "$DB" "SELECT * FROM http_latest_results LIMIT 10;"
```

---

## 6. systemd 服务

```ini
# /etc/systemd/system/xray-knife-proxy.service
[Unit]
Description=xray-knife local SOCKS proxy (127.0.0.1:9999)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/lib/xray-knife-run.sh
Restart=always
RestartSec=10
RuntimeDirectory=xray-knife

[Install]
WantedBy=multi-user.target
```

**开机竞态修复**（`10-wait-network.conf`）：
```ini
[Unit]
After=NetworkManager-wait-online.service
Wants=NetworkManager-wait-online.service
StartLimitIntervalSec=300
StartLimitBurst=10
[Service]
RestartSec=15
```
> 原因：`network-online.target` 可能在网络**真正可路由之前**就被判定到达，
> 导致 xray-knife 启动时 DNS 不可用而失败。加明确的等待依赖解决。

**常用操作**：
```bash
systemctl status xray-knife-proxy
systemctl restart xray-knife-proxy
journalctl -u xray-knife-proxy -f
journalctl -u xray-knife-proxy -b --no-pager | tail -30
```

---

## 7. 故障排查

### 代理不通

```bash
# ① 服务在跑吗
systemctl is-active xray-knife-proxy

# ② 端口在听吗
ss -ltnp | grep 9999

# ③ 凭据就绪吗（服务刚启动时可能还没生成，等 5-10 秒）
cat /run/xray-knife-proxy.env

# ④ 直接测（绕开 pt35-proxy）
. /run/xray-knife-proxy.env
curl -v --socks5-hostname 127.0.0.1:9999 \
     --proxy-user "$XRAY_SOCKS_USER:$XRAY_SOCKS_PASS" \
     https://www.google.com/generate_204

# ⑤ 看日志（会显示用了哪个节点、轮换倒计时）
tail -40 /run/xray-knife-proxy.log

# ⑥ 重启
systemctl restart xray-knife-proxy && sleep 10 && pt35-proxy test
```

### 所有节点都失败

```bash
pt35-proxy update      # 先更新订阅
pt35-proxy retest      # 重新测速（会重排 valid.txt）
pt35-proxy restart
```

### 二进制损坏（本机踩过！）

**症状**：`SIGILL: illegal instruction`，指令字节全是 `0x0`。
**原因**：非正常断电导致文件内容损坏（尺寸正常但内容是错的）。
**修复**：
```bash
# 校验
sha256sum /usr/local/bin/xray-knife
# 应为 af48951ec9e187acbb28211551532cad4fd25001a181e4fee2d2481792feef09

# 重下（aarch64）
cd /tmp
curl -LO https://github.com/xray-knife/xray-knife/releases/latest/download/Xray-knife-linux-arm64-v8a.zip
unzip -o Xray-knife-linux-arm64-v8a.zip
install -m755 xray-knife /usr/local/bin/xray-knife
systemctl restart xray-knife-proxy
```

> **教训**：本机因非正常关机损坏过 300+ 文件，特征是
> **"文件大小正确、头部正常、但内容错误"**，普通检查查不出来。
> 用 `pt35-healthcheck --full` 做全量校验。

### 凭据相关

```bash
# 凭据文件被删/损坏 → 重启服务会重新生成
systemctl restart xray-knife-proxy
```

---

## 8. 安全提示

| 项 | 建议 |
|---|---|
| **订阅 URL** | 含 token，**不要提交到 git**、不要贴到公开场合 |
| **SOCKS 端口** | 只监听 `127.0.0.1`（不对外），✅ 安全 |
| **凭据** | 每次随机，`/run` 是 tmpfs，重启即消失 |
| **`/etc/xray-knife/socks-credentials`** | 旧固定凭据，服务已不用 —— 可以留着也可以删 |
| **订阅服务商** | `node1.example.com` / `node2.example.com` —— 注意隐私与合规 |

---

## 9. 快速参考卡

```bash
# 日常
pt35-proxy                       # 状态一览
pt35-proxy run <cmd>             # 单命令走代理
source /usr/local/bin/proxyenv   # 整个 shell 走代理

# 维护
pt35-proxy update                # 更新节点
pt35-proxy retest                # 重测速
pt35-proxy restart               # 重启

# 排查
tail -40 /run/xray-knife-proxy.log
journalctl -u xray-knife-proxy -b | tail -30
sqlite3 /root/.xray-knife/xray-knife.db "SELECT * FROM subscriptions;"

# 深度
xray-knife subs show
xray-knife http --from-db
xray-knife parse "vless://..."
xray-knife db backup
xray-knife webui                 # 图形界面（浏览器开）
```

# 164.30.6.242：最多十人 Live Voice 测试部署评估

> 2026-09-07，只读观察；首份主机快照约为 08:28 UTC。
> 结论：硬件适合作为十人受控测试的部署起点；公网 HTTPS 和十人 Live Voice
> 尚未部署或验证。建议每位测试者使用独立实例，以 1 → 3 → 10 人逐级验收。

## 任务边界

用户要求先了解新服务器状态，再判断如何部署 JiuwenSwarm，使最多十人通过
浏览器打开 Web UI 测试 Live Voice。此次为 Tier 0 调研/文档范围；按“最多十人
同时使用”提出容量方案，不新增产品认证协议或修改运行服务。

通过指定 SSH 密钥，以 `hongxing` 成功连接。检查主机资源、服务元数据、端口、
公开静态资源、WebSocket 初始握手和无凭据外连；未发送聊天/Agent/Tool/Task
请求，未运行付费模型推理，未安装软件或改动远端配置。密钥和私有配置未输出。

本地参考源码为 `ebeb5aa4db828b69489ce205de85ebd1d3a1c5a5`，工作区初始干净，
分支 `hx/0812_live_voice_w3` 比上游领先 2 个提交。远端源码目录权限不足，
其实际 commit/依赖/Live Voice 运行合同未知。本地源码仅用于新部署设计依据。

## 服务器实际状态

| 项目 | 实测 |
|---|---|
| 主机 | `ecs-daily-dev-swarm`；Ubuntu 24.04.4 LTS；Linux 6.8.0-138；x86_64 |
| CPU/内存 | 32 个逻辑 CPU；约 60 GiB 内存，已用 2.8 GiB，可用约 58 GiB；无 swap |
| 磁盘 | 根分区 ext4，1008 GiB，已用 6.6 GiB，可用约 961 GiB |
| 负载 | load average `0.00 / 0.00 / 0.00`；连续运行约 4 天 20 小时 |
| 网络地址 | `enp0s3: 192.168.0.88/24`；Tailscale `100.123.45.63/32`；公网 SSH 使用 `164.30.6.242` |
| 基础工具 | Python 3.12.3、Node 20.20.2、npm 10.8.2、Git 2.43.0、uv、Tailscale |
| HTTP 代理 | Nginx 1.24.0 已安装，service inactive/disabled；仅启用目录中的默认配置 |
| 容器运行时 | PATH 未找到 Docker；`/usr/bin/docker`、`/usr/bin/podman` 均不存在 |
| 管理权限 | `hongxing` 属于 sudo 组；`sudo -n -l` 返回 `a password is required` |

现有服务为 `jiuwen@co-scribe.service`，运行用户/组 `jw-co-scribe`，启动模板
`/etc/systemd/system/jiuwen@.service` 使用：

```text
WorkingDirectory=/srv/jiuwen/%i/src
EnvironmentFile=/srv/jiuwen/%i/env
ExecStart=/srv/jiuwen/%i/src/.venv/bin/jiuwenswarm-start
Restart=on-failure; RestartSec=5
CPUQuota=150%; MemoryMax=4G; TasksMax=512; NoNewPrivileges=yes
```

该实例约占 1.18 GiB 内存、134 个任务/线程，systemd 记录自动重启次数为 0。
`PrivateNetwork/PrivateTmp/ProtectHome/ProtectSystem` 均未启用，未设置
IPAddressAllow/Deny。因此不能把“独立 Linux 用户”当作完整的跨实例工具隔离。
`/srv/jiuwen/co-scribe` 为 `0750`，当前账号读取其源码/环境文件遭到拒绝。

### 现有入口与实际响应

| 入口 | 状态 |
|---|---|
| `127.0.0.1:6173` | HTTP 200，页面 title 为 `WorkSwarm` |
| `127.0.0.1:19092 / :20000 / :20001` | 均监听；与默认端口偏移一组的服务拓扑相符，具体进程参数未读取 |
| Tailscale | tailnet-only HTTP `ecs-daily-dev-swarm.tailadfeb9.ts.net`，代理至 `127.0.0.1:6173` |
| WebSocket | 通过 `6173/ws`，使用现有 Tailscale Origin，返回 HTTP 101 和 `connection.ack`；随后关闭 |
| 公网 80/443 | 从本机探测均未连通；服务器无 443 监听，80 仅监听 Tailscale 地址 |
| DNS | `swarm.164.30.6.242.sslip.io` 的 A 记录为 `164.30.6.242` |
| 模型 API 出站 | 无凭据请求 `https://api.openai.com/v1/models` 返回 401，TLS 校验通过；只证明网络/TLS，不证明密钥、模型权限或配额 |
| 源码/包出站 | GitCode 和 npm registry HTTPS 均返回 200；不证明完整依赖安装成功 |

主 JavaScript 为 `/assets/index-DvJYFoPm.js`，3,618,377 字节，SHA-256：
`3a3e68b20bc98173d87e38bc30625a144aa086a1c770d1c9b42c726598956a92`。
该资源未发现 `live_voice.composition`、`/ws/live-voice/media`、
`openai-realtime-native`、`gpt-realtime-2`、`live_voice.task` 字面量。
这不能代替完整构建/后端核对；目前没有证据证明现有实例包含本地 Live Voice 候选。

## 推荐架构与理由

推荐给十位受邀测试者各分配一个隔离实例、独立数据目录/项目/授权身份和登录账号，
共用只读的同一版本程序镜像。使用 Nginx 的 HTTPS 入口按主机名分发：

```text
测试者 01 → https://lv01.164.30.6.242.sslip.io → 登录校验 → 实例 01
测试者 02 → https://lv02.164.30.6.242.sslip.io → 登录校验 → 实例 02
   …
测试者 10 → https://lv10.164.30.6.242.sslip.io → 登录校验 → 实例 10

每个实例：Web UI / HTTP 代理 → Gateway / WebChannel → AgentServer
                                      → Speech / Native / Agent Provider
                                      → 本实例授权测试项目及任务库
```

以上是规划地址，尚未配置证书或服务。采用独立主机名可保持当前根路径、同源
WebSocket、浏览器存储和麦克风许可边界；无需先改造应用以支持 `/user01/` 子路径。

不建议把现有 co-scribe 实例直接开放给十人共享。参考源码的
[P3 环境构造](../../jiuwenswarm/server/live_voice/p3_authenticated_composition.py)
创建单个 static bearer principal、授权项目集合和到期时间；
[Gateway](../../jiuwenswarm/gateway/app_gateway.py)为受控 Web Live Voice 请求
注入实例级凭据。给前置代理增加十个账号不会自动产生十套应用权限和数据隔离。
[STATUS](../STATUS.md)也未认定生产认证/租户隔离完成。

建议部署实现采用**每人一个独立容器网络和数据卷**：

- 每个实例拥有自己的 network namespace；内部 AgentServer/Gateway 端口不发布。
  仅 Web HTTP 服务发布到宿主机 loopback，例如 `127.0.0.1:26101` 至 `26110`，
  供宿主机 Nginx 使用；部署前重新检查这些规划端口未占用。
- 每人一套数据目录、配置、P3 token/principal/project IDs/database 和授权有效期。
  容器内采用相同路径布局，挂载各自项目；程序镜像相同，不能共用可写工作区/任务库。
- 容器运行非 root 用户，不使用 host network，不挂载 Docker socket、其他实例
  数据或宿主机家目录；跨实例端口和文件访问必须有实测拒绝证据。
- 十个实例不加入同一个可互通的 bridge 网络。Docker 的
  [网络说明](https://docs.docker.com/engine/network/drivers/bridge/)
  明确区分同网络互通和跨网络隔离；发布端口也必须明确绑定 loopback。
- 每个域名的登录只允许对应测试账号，保护所有 HTTP、文件接口、`/ws` 和
  `/ws/live-voice/media`。可从 Nginx
  [HTTP Basic authentication](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html)
  开始；须通过实际浏览器验证认证后的 WSS。共用一个包含十人的密码文件且不做
  域名授权，会让十人都能访问彼此实例，不能算隔离。

上述是受控内部测试部署方案，不宣称生产多租户安全认证。单独 Linux 用户加
systemd 的方式虽更接近现有运维，但还需解决工具访问其他 localhost 服务等
边界，不能仅复制现有 unit 就获得等价隔离。容器运行时目前未安装，正式执行
涉及主机网络规则变更，需验证已有 Tailscale/co-scribe 路由仍正常。

### HTTPS 与端口注意事项

浏览器采集麦克风需要安全上下文和用户许可；现有 Tailscale 的普通远端 HTTP
入口不能直接作为公网麦克风测试入口，参见
[MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。
Nginx 应保留全部应用路径和 WebSocket Upgrade，设置适合长连接的超时，参见
[Nginx WebSocket 代理说明](https://nginx.org/en/docs/http/websocket.html)。

本机 Nginx 默认配置含 `listen 80 default_server` 和 `listen [::]:80`；
Tailscale 已占用其地址的 80 端口。部署时应核对云 EIP 到 `192.168.0.88` 的映射，
让新入口明确绑定对应主网卡地址，处理默认 wildcard listener，避免占用现有
Tailscale listener。公网 EIP 本身未出现在本机地址列表，不应盲目把它作为 bind 地址。

还需核对云安全组/主机防火墙对预期客户端开放 443，以及证书 HTTP-01 验证所需
的 80；保留现有 SSH 管理规则。十个名称需要可信证书和续期验证。Origin allowlist
按实例配置相应主机名，不能复制 localhost 值或关闭校验来使连接“成功”。

## 容量判断与上线验证

硬件资源足以开始该规模的试部署，但没有十人并发实测。建议初始每个实例设
**2 CPU 的计算上限、4 GiB 内存上限**，十个实例共 40 GiB 内存上限，为现有
实例、OS、代理和缓冲留出余量。它们是规划限额，不是实际峰值测量或性能保证；
镜像构建先单独完成，避免十份并行构建挤占运行资源。

同时记录实例实际内存、CPU、事件循环延迟、断线/音频错误、模型 429 和响应时间。
真实瓶颈还包括云出口带宽、Provider 并发与音频/文本配额、模型耗时和工具负载。
十套实例使用同一个 Provider 项目时，配额可能仍然共享；增加实例不会增加配额。
单个 Speech Provider 对象的活跃资源也有界：
[StreamingSpeechConformance](../../jiuwenswarm/server/live_voice/streaming_speech.py)
默认识别/合成各 8，不能将这一对象级数字误解为已证明的整机人数上限。

执行顺序：

1. 明确可用的 sudo 管理方式、Provider 私有配置与模型权限/配额、测试账号名单、
   测试域名及证书方式；保留已有 co-scribe 的服务和数据。
2. 固定新的 Live Voice 源码 commit、Python/SDK 锁定版本和前端
   `build:live-voice` 产物，制作可复用镜像。现有服务器源码不可读，不能假定
   其代码已是所需候选。Linux 启动需实现并验证受控启动器的同等配置/preflight
   合同，而非直接把 Windows 启动命令替换为一个裸启动命令。
3. 先部署一个实例及 HTTPS/WSS 登录入口。在独立无 remote 测试项目上完成
   文字 → 真实 Agent/工具，以及麦克风 final speech → 真实 Agent/工具 →
   结果 → 可听语音；验证所选 Native/Cascade 路线、打断、退出和重连。
4. 扩至三人，验证同时讲话、各自任务/通知/文件/模型设置、错误账号/Origin 和
   跨实例工具访问的拒绝效果，再扩至十人并做持续使用、掉线和恢复测试。
5. 只有同一镜像/配置下十人完整链路通过，才标记“十人测试环境可用”。账号数量
   与 WebSocket 数量不同，不能简单把代理连接数限制为 10；一位用户可持有多条连接。

详细配置依赖见
[部署依赖核查](REMOTE_LIVE_VOICE_DEPLOYMENT_AUDIT_20260907.md#本地源码确认的部署依赖)，
其旧 IP 连接故障不适用于本服务器。启动和完整验收继续服从
[运行手册](../runbooks/E2E_RUNBOOK.md)、
[人工 Journey](../demo/PRODUCT_READINESS_SHOWCASE.md)及
[验收合同](../validation/PRODUCT_READINESS_ACCEPTANCE.md)。

## 本次完成与保留项

已完成服务器状态评估、现有页面/控制连接验证、网络与权限限制识别及十人部署
建议。没有读取到现有源码/私有配置，没有验证 Speech/Native/Agent 密钥，没有
公网 HTTPS、真实音频、十人并发或隔离验收信用。此次只新增评估文档，不改变
当前产品完成度；正式部署与其配置/隔离实现应作为下一执行范围。

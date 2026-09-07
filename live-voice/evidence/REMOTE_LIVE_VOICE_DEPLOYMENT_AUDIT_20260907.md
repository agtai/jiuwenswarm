# 远程 Live Voice 部署核查：164.30.22.108

> 2026-09-07；本次证据状态：BLOCKED — SSH 与 HTTPS 网络入口未连通。
> 本文记录本次观察和恢复连接后的核查清单，不是服务器实际部署说明或部署成功证明。

## 范围与证据边界

用户要求使用指定 SSH 身份检查现有 JiuwenSwarm 服务，确认其他人如何通过
`https://swarm.164.30.22.108.sslip.io/` 使用 Live Voice，并确定另一台服务器
复现相同效果的条件。

本次可完成的边界是只读连接诊断、源码依赖核对和文档记录（Tier 0）。
验收需要原服务器实际部署清单、外部浏览器完整语音链路，以及目标服务器的
对应实测。运行服务、账户、网络策略、数据和源码均未改动；未运行真实
Provider 调用、Agent、Tool 或 Task。尚未提供第二台服务器的连接信息。

本地源码基线为 `26eb034bc3df0f66a9896942bb15efde356691f9`，分支
`hx/0812_live_voice_w3`。核查开始时工作区干净，和上游 ahead/behind 为 `0/0`。
远端源码版本、操作系统、进程、部署方式和运行数据均未知；不能从本地源码推定。

## 已执行检查

| 检查 | 本次结果 | 结论边界 |
|---|---|---|
| 指定本地 SSH 私钥路径 | 文件存在；未打印密钥内容 | 不证明服务器接受该密钥 |
| SSH 实际配置 | 用户 `hongxing`，目标 `164.30.22.108:22` | 尚未确认是否需非默认端口、VPN 或跳板机 |
| SSH，15 秒连接超时；另一次 8 秒重试 | 均为 `Connection timed out` | 未进入主机身份确认或用户认证阶段 |
| 域名 A 记录 | `164.30.22.108` | DNS 解析符合给定地址 |
| TCP 22、80、443 | 本机连接均未成功 | 不能区分云安全组、主机防火墙、路由、实例/EIP 状态或来源限制 |
| HTTPS HEAD，15 秒连接超时；另一次 6 秒重试 | 均超时 | 未取得 HTTP 响应或证书；不证明所有网络来源均不可访问 |
| 同机普通外网 HTTPS 对照 | `https://example.com` 返回 HTTP 200 | 本机并非完全无法访问外网 HTTPS |

应先确认 SSH 端口/VPN/跳板机要求，或通过云控制台核对实例运行状态、EIP
绑定、路由和安全组。SSH 来源应匹配管理员的实际出口；HTTPS 来源应覆盖预期
访问者。若部署使用 ACME HTTP-01 验证或 HTTP 跳转，还需核对 80 端口。
未登录服务器前不能把故障归因于 Nginx、Caddy、JiuwenSwarm 或密钥。

## 本地源码确认的部署依赖

下列端口是本地源码/运行手册的默认值，尚未在该服务器上核实。

```text
外部浏览器：HTTPS 页面 + 同源 WSS
  → TLS 反向代理（当前服务器实现未知）
  → Web HTTP 服务，默认 5173：静态资源和应用 HTTP 接口
  → Gateway 的 WebChannel，默认 19000：/api、/ws、/ws/live-voice/media
  → AgentServer，默认 18092
  → 真实模型 / Speech Provider / 授权项目的 Agent 与工具

Gateway 默认 19001：其他 Gateway WebSocket 入口（/acp、/tui）。
```

- **安全上下文与同源路由：** 浏览器麦克风需要安全上下文和用户许可。
  HTTPS 证书必须有效，浏览器实际连接应使用同源 WSS。
  [Web 服务实现](../../jiuwenswarm/channels/web/app_web.py)代理 `/api` 和
  `/ws` 前缀，同时处理 `/file-api/`、`/share-api/`；部署不能只复制静态
  `dist` 而遗漏应用接口。专用媒体路由是
  [`/ws/live-voice/media`](../../jiuwenswarm/gateway/live_voice/dedicated_media_registration.py)。
- **Origin 配置：** [校验代码](../../jiuwenswarm/common/security/ws_origin.py)
  使用 `JIUWENSWARM_ENABLE_ORIGIN_CHECK=1` 和
  `JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS`。后者是逗号分隔的主机名，
  因此公网部署需要相应域名；不能照搬受控启动器的 `localhost,127.0.0.1`。
  该校验按 hostname 匹配，本身不证明完整 scheme/port、登录或租户隔离。
- **构建身份：** [前端包](../../jiuwenswarm/channels/web/frontend/package.json)
  的 `npm run build:live-voice` 使用
  [`.env.live-voice`](../../jiuwenswarm/channels/web/frontend/.env.live-voice)，
  开启 Integrated Web、P1、P3 mutation 和 generation interruption。
  普通构建不是等价替代。需记录实际服务的 asset 哈希、构建模式和环境覆盖值。
- **后端运行合同：** [受控启动器](../../scripts/live_voice/start_hands_free_demo.ps1)
  配置 product composition、P2、P3 text/mutation、critical input、dedicated
  media、end-of-turn、Web Alpha credential 和正式 batch/streaming speech。
  Linux 部署需要核对其实际启动方法与同等运行合同；该 PowerShell 启动器的
  存在不能证明 Linux 已支持相同受控启动与验证流程。
- **语音与 Agent 配置：** Speech Provider 凭据、STT/TTS 模型与语音、
  Agent 模型、Native/Cascade 引擎选择都属于运行状态。
  Native 引擎配置项包括 `LIVE_VOICE_INTERACTION_ENGINE` 和
  `LIVE_VOICE_NATIVE_REALTIME_MODEL`；参见
  [配置实现](../../jiuwenswarm/server/live_voice/native_interaction_config.py)。
  只记录模型等非敏感值以及凭据是否存在，不把密钥放进前端、报告或 Git。
- **授权和持久化：** 核对 `JIUWENSWARM_DATA_DIR`、配置目录、P3 database、
  principal、project IDs、授权到期时间和 Executor profile。真实 Code 项目
  必须在目标机器注册，目录存在且权限正确。项目路径、注册和私有配置不能靠
  Git 自动恢复；Session/Task/结果/ACK 的迁移需保持一致性。
- **精确依赖：** [pyproject.toml](../../pyproject.toml)要求 Python
  `>=3.11,<3.14`，部分依赖使用版本下界和 Git develop 分支。
  [uv.lock](../../uv.lock)记录本地 openjiuwen Git 修订
  `94e10cb6102c36fe78a64547957c0def97299273`。需核对服务器实际安装版本、
  SDK 补丁、Python/Node 版本和前端锁文件；仅重新安装最新依赖不能保证一致。

浏览器要求参考 [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。
如实际使用 Caddy，可按其 [WebSocket 代理说明](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
和 [自动 HTTPS 条件](https://caddyserver.com/docs/automatic-https)核查；这不表示
当前服务器已经使用 Caddy。

## 恢复连接后需要取得的原服务器清单

| 边界 | 需要确认并保存的非敏感事实 |
|---|---|
| 主机与监督机制 | OS/架构/资源、运行用户、systemd/Docker/其他启动方式、开机启动和故障重启配置 |
| 程序身份 | 实际源码目录与 commit、工作区改动、Python 环境、依赖实际版本、SDK 补丁、前端资产哈希 |
| 服务连接 | 实际监听地址/端口、启动入口、服务依赖、Gateway 到 AgentServer 的连接确认 |
| 公网入口 | Nginx/Caddy/负载均衡的脱敏配置、路由、WebSocket Upgrade/超时、TLS 证书域名/到期/续期机制 |
| 语音配置 | 实际构建开关、进程生效的非敏感开关、Speech/Native/Agent 模型与 Provider 连通性 |
| 数据与项目 | 数据卷/目录、项目注册和实际路径、持久化库、备份/恢复方法、权限和运行任务状态 |
| 访问边界 | 谁可以进入页面和调用 Agent/工具、principal/project 绑定、令牌有效期、不同用户/浏览器的隔离程度 |

不能直接输出完整环境、配置文件、容器 inspect 或日志；应在服务器端筛选和
脱敏后仅返回核查所需事实。备份凭据和运行数据应通过受控渠道处理。

## 换机复现与验收顺序

1. 先固定原机实际源码、依赖、构建和运行合同，再准备目标服务器。确定是使用
   新 IP 对应的新域名，还是迁移可保留的域名/EIP；换 IP 不会自动使包含旧 IP
   的 `sslip.io` 名称指向新服务器。
2. 按原机监督机制配置服务和持久化目录，注入私有凭据，恢复或重新注册项目。
   目标路径变化需修正相应注册和授权。不得让两个实例无协调地写同一任务库。
3. 配置目标域名、可信证书、同源 HTTP/WSS 和 Origin 主机名。
   内部服务端口以本机或受控内部网络访问；核对入口访问规则和全部应用接口。
4. 从独立客户端确认页面/资产身份和安全上下文，`/ws` 收到
   `connection.ack`，媒体路由在合法会话/授权下完成连接。
   端口监听或 HTTP 200 不替代后端 readiness；19001 没有可依赖的 HTTP `/health`。
5. 在已注册的可丢弃无 remote 项目中验证文字 → 真实 Agent → 工具结果，再验证
   真麦克风 final speech → 真实 Agent/工具 → 正确结果 → 可听见的语音。
   分别覆盖部署声明支持的 Native/Cascade；ASR/TTS 独立成功只证明语音子链路。
6. 用第二个独立浏览器/用户验证访问与声明的隔离边界；验证错误 Origin、过期或
   错误授权不能产生 Agent/Tool/Task/受保护状态副作用。页面公开可访问不等于
   已具备生产级多用户授权。
7. 验证中断、重连、任务通知、结果下载和数据保留；重启/恢复验证前排空真实任务，
   使用可恢复数据。记录原机和目标机同一验收场景的实际结果。

完整人工 Journey 和候选验收仍由
[演示合同](../demo/PRODUCT_READINESS_SHOWCASE.md)、
[验收合同](../validation/PRODUCT_READINESS_ACCEPTANCE.md)与
[运行手册](../runbooks/E2E_RUNBOOK.md)负责。
[STATUS](../STATUS.md)的生产认证/租户隔离和物理验收缺口不能因 HTTPS 部署而关闭。

## 本次收口

连接诊断与源码部署依赖核对完成。原机实际部署审计、公网 Live Voice 可用性、
第二台服务器部署及完整等价性验收均未完成，需要先恢复服务器连接并取得目标机信息。
本文不新增产品策略，不修改当前产品完成度，不触发远程 Git 更新。

---
name: delayed-restart-app
description: 在用户要求或已接受重启 JiuwenSwarm 服务时，使用 detached launcher 安排延迟重启；当前会话会断开。
---

# 延迟重启 JiuwenSwarm

此操作终止并重新拉起当前 Agent 所在服务。先说明当前连接会断开，确认目标是本次授权的 JiuwenSwarm app 进程；不要仅凭端口、进程名或历史 PID 结束其他服务。普通配置查询或故障诊断不自动授权重启。

使用本目录 [launch_delayed_restart.py](launch_delayed_restart.py)，它以 detached 方式启动 `jiuwenswarm.scripts.delayed_restart_app`，避免随被重启进程一起终止。使用已核实的 app PID：

Windows PowerShell：

```powershell
python "$env:USERPROFILE\.jiuwenswarm\agent\workspace\skills\delayed-restart-app\launch_delayed_restart.py" --pid <PID> --delay 5
```

Unix/macOS：

```bash
python ~/.jiuwenswarm/agent/workspace/skills/delayed-restart-app/launch_delayed_restart.py --pid <PID> --delay 5
```

技能实际安装位置不同则使用本目录的绝对路径。不要在 PowerShell 中使用 cmd 的 `%USERPROFILE%` 语法。延迟可按需求调整，默认 5 秒用于返回响应。

只在 launcher 成功后声明“已安排重启”。服务真正恢复需要后续连接/健康证据；当前连接断开不是恢复成功的证明。

# 测试环境搭建

从零把一台机器配到能跑完整测试套件与 UI 端到端测试。每一条约束下面都写了不这么做会发生什么——它们全部来自实际踩过的坑，不是预防性建议。

## 一、Python 必须是 3.11

```bash
uv sync --python 3.11 --extra test --extra clouddoc --extra desktop --extra ssh --extra a2a --extra shell-ast
```

**不能让 uv 自己挑版本。** `pyproject.toml` 允许 `>=3.11,<3.14`，uv 默认会取上限附近的 3.13，然后：

`pytest.ini` 里 `filterwarnings = error`。Python 3.12 起，无效转义序列从 `DeprecationWarning`（被该配置忽略）升级成了 `SyntaxWarning`（被该配置视为错误）。第三方库 `pysbd` 的 `segmenter.py` 里有一处 `'{0}\s*'`，于是它一被导入就抛 `SyntaxError`，**144 个测试文件收集失败**。报错指向 site-packages，看不出跟 Python 版本有关，很容易误判成依赖装坏了。

## 二、extra 的作用与漏装后的表现

| extra | 缺了会怎样 |
|---|---|
| `test` | 没有 pytest 及其插件 |
| `desktop` | 缺 `pywebview`，4 个 desktop 测试**收集报错**（不是跳过） |
| `clouddoc` | 缺 `googleapiclient`。离线单测**照常全绿**，只有真实 API 路径不可用——最容易漏装的一个 |
| `ssh` / `a2a` / `shell-ast` | 对应模块的测试收集失败 |
| `tui` | **装不上**（`jiuwenswarm-tui` 不在公共源）。测试里只有字符串断言，不影响 |

`dev` extra 只在打包（pyinstaller）时需要，测试用不到。

## 三、依赖源：gitcode 可能拉不动

`openjiuwen` 依赖写死指向 `https://gitcode.com/openJiuwen/agent-core.git@develop`。境外网络下反复 TLS 中断（`GnuTLS recv error`、`early EOF`），uv sync 直接失败。

该仓在 GitHub 有同源镜像。本地已 clone 过 `agent-core` 时，把 URL 重定向过去即可——两边是同一个 commit：

```bash
export GIT_CONFIG_COUNT=1 \
       GIT_CONFIG_KEY_0=url.file:///path/to/agent-core.insteadOf \
       GIT_CONFIG_VALUE_0=https://gitcode.com/openJiuwen/agent-core.git
uv sync ...
```

用 `GIT_CONFIG_*` 环境变量而非 `git config`，作用域只限这一条命令，不污染全局配置。

## 四、跑测试

```bash
uv run pytest --no-cov -q                 # 全套，约 3 分 40 秒
uv run pytest --no-cov -q -k clouddoc     # 单一特性
```

**基线：5326 passed, 35 skipped。**

`--no-cov` 让回归从约 30 秒降到约 4 秒（单特性口径）。

**盯 passed 的绝对数，不要只看退出码。** 全部跳过和全部通过的退出码都是 0——本仓曾经因为一个越界的 conftest hook，在无凭证的机器上把 5361 个测试全部静默跳过，CI 一直是绿的。详见设计仓 `co-scribe-incident-test-isolation.md`。

**报数字时连命令口径一起报。** 只跑两个子目录得到的数，和全树跑得到的数，不是一回事。

## 五、UI 端到端

### 额外前置

```bash
uv pip install playwright                  # 未被任何 extra 声明
uv run playwright install chromium         # 约 389 MB
sudo uv run playwright install-deps chromium   # 12 个系统库，需要 root
cd jiuwenswarm/channels/web/frontend && npm install && npm run build
```

`SKILL.md` 让装的 `.[e2e]` extra **在 pyproject.toml 里不存在**，照做会失败；直接装 `playwright` 即可。

Node 无需 root：官方 tarball 解到 `~/.local/node`，把 `bin/` 链进 `~/.local/bin`。

Chromium 的系统库（`libatk-1.0.so.0`、`libgbm.so.1`、`libasound.so.2` 等 12 个）**必须用系统包管理器装**，浏览器否则一启动就 `error while loading shared libraries`。这是整条链路上唯一需要 root 的一步。

### 用临时 HOME 跑，并且要播种

```bash
uv run python tests/ui_e2e/todo_ui_report.py \
  --home /tmp/e2e-home --runtime-python .venv/bin/python \
  --report-dir /tmp/e2e-report
```

`--home` 的默认值是 `Path.home()`，也就是**你的真实工作区**。E2E 会在其中起服务、建会话、删会话目录；clouddoc 若为开启状态，watcher 会去轮询你纳管的真实云文档。**务必显式传 `--home`。**

临时 HOME 需要在 `<home>/.jiuwenswarm/config/` 下预置三样，否则跑不起来：

1. **`.env`** —— 可用的 `API_BASE` / `API_KEY` / `MODEL_NAME` / `MODEL_PROVIDER`。出厂值指向 `example.com`，后端会把那个 HTML 页面当成 API 响应
2. **`config.yaml`** —— 从真实配置复制，但**把 `clouddoc.enabled` 设为 false、`connections` 清空**，免得跑测试碰真实云文档
3. **`setup_guide.enabled: false`** —— 全新工作区会弹首次配置引导浮层，挡住会话建立。注意是**嵌套键**（后端读的是 `setup_guide.enabled`），写成顶层 `setup_guide_enabled` 无效

**模型配置缺失时会被静默顶替。**`config.yaml` 的 `models.enable_free_models` 默认为 `true`，
含义是「实时拉取可用的免费模型」。于是 `.env` 里的模型配置一旦失效或被重置回出厂占位值
（`example.com` / `your-model-name`），应用**不会报「没配模型」，而是自动换一个免费模型继续跑**。

这在测试里格外危险，因为失败现象与根因相距很远：本轮排查 UI E2E 时，界面显示的模型是
`DeepSeek V4 Flash`——没有人配过它——并报 `Upstream request failed: Model is unavailable`。
表面看像端点故障，实际是临时 HOME 的 `.env` 被应用回写重置，免费模型机制接管所致。

更隐蔽的是它成功的时候：**测试可能"跑通了"，但用的是与你指定的完全不同的模型**，
而报告里不会有任何提示。为测试播种的工作区建议一并设 `models.enable_free_models: false`，
让模型配置错误以失败的形式暴露，而不是被悄悄绕过。

另有两项同类回写：应用会把 `setup_guide.enabled` 改回 `true`，也会重置 `.env`——
播种过的临时 HOME 在跑过一次之后需要复核这三项，不能假定写进去就一直有效。

第 2、3 条都源于同一件事：**这套 E2E 原本是围绕"跑在真人用过的工作区"写的**，干净环境会把它的隐式前提逐个暴露出来。

## 六、GPU（可选）

机器上有 RTX 2080 Ti，但当前由开源 `nouveau` 驱动接管，无 NVIDIA 驱动。测试套件与 UI E2E **都不需要 GPU**。

若要本地推理，装驱动即可——PyTorch / vLLM 的 pip wheel 自带 CUDA 运行时，完整 CUDA Toolkit 只在需要 `nvcc` 编译自定义算子时才装。

## 七、当前已验证的环境

| | |
|---|---|
| Python | 3.11.16（uv 0.12.5 托管） |
| pytest | 9.0.3 + asyncio 1.3.0 / cov 7.1.0 / mock 3.15.1 / html 4.2.0 |
| clouddoc | google-api-python-client 2.198.0、google-auth 2.49.2 |
| desktop | pywebview 6.2.1（仅够跑测试；真开窗口还需 GTK/Qt 绑定与显示服务，本机均无） |
| 其他 | asyncssh 2.23.1、a2a-sdk 1.0.0、tree-sitter 0.25.2 |
| E2E | playwright 1.62.0、chromium-1234（系统库 0 缺失）、node v24.19.0、前端已构建 |

全套 **5326 passed / 35 skipped**；UI E2E 可完整跑完并产出截图与报告。

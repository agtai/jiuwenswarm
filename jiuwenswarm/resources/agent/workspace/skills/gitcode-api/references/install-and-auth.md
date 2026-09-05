# 安装与认证

仅在当前 CLI 缺失、版本或认证失败时使用。工程 pyproject.toml 声明 gitcode-api>=1.2.20；实际方法以当前 CLI --help 为准，旧文档中的 1.2.14/1.2.16 不作为升级目标。

优先复用已安装 CLI 与环境；安装/升级属于任务需要且当前授权允许时，可用 pip/uv 安装工程要求的版本，或用 uvx 临时运行。不要为只读说明任务安装软件。

认证使用 GITCODE_ACCESS_TOKEN，位置由当前 host 的配置/secret 管理确定，不把历史 ~/.jiuwenclaw/config/.env 路径当成本机事实。用户在本机填写凭据；不打印 token、不通过命令行参数传明文、不自动创建令牌或提高权限。

企业证书可用 GITCODE_CA_BUNDLE / REQUESTS_CA_BUNDLE 指向有效 CA 文件。CLI 不暴露 Python SDK 的 decrypt 或自定义 http_client；特殊 SDK 用法需明确该调用能力，不虚构 CLI 参数。缺少权限时报告实际失败，继续不依赖权限的工作。

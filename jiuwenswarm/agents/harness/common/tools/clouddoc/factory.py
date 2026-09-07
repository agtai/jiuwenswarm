"""Pick the provider a connection's credentials describe.

A connection is one vendor and one account, and the credentials file is what says
which vendor: a Google service account key is JSON carrying ``type:
"service_account"``, while a Feishu app is an id and a secret. Reading it beats adding
a vendor field to the config, which would let the two disagree -- and the file is the
thing that actually decides what the calls can do.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import ProviderError

logger = logging.getLogger(__name__)


# The two connection kinds (design §13, matrix S.1). ``service`` is a service
# account or a Feishu app acting as its bot; ``personal`` is a person's own account.
CONNECTION_KINDS = ("service", "personal")


def _load(credentials_file: str) -> dict:
    try:
        with open(credentials_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ProviderError("invalid", f"无法读取凭证文件 {credentials_file}：{exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError("invalid", f"凭证文件不是对象：{credentials_file}")
    return data


def detect_kind(credentials_file: str) -> str:
    """``"service"`` or ``"personal"``, from the file's own ``kind`` field.

    A personal Feishu file carries **no secret**: only ``kind``, ``brand`` and the
    identity it was verified as (open_id, name); the token lives in the platform
    CLI's own store (``lark-cli auth login``), so a copied file grants nothing by
    itself. A personal Google file is Google's ``authorized_user`` shape -- the
    refresh token and the OAuth client that issued it -- written mode 0600.
    Absent ``kind`` means service (or ``authorized_user``, which is personal by
    construction) -- every file written before the field existed.
    """
    data = _load(credentials_file)
    kind = str(data.get("kind") or "").strip().lower()
    if not kind:
        kind = "personal" if data.get("type") == "authorized_user" else "service"
    if kind not in CONNECTION_KINDS:
        raise ProviderError("invalid", f"未知的连接类型 {kind!r}（可选 service / personal）。")
    return kind


def detect_vendor(credentials_file: str) -> str:
    """``"google"`` or ``"feishu"``, from the credential file's own shape."""
    data = _load(credentials_file)
    if str(data.get("kind") or "").strip().lower() == "personal":
        brand = str(data.get("brand") or "").strip().lower()
        if brand in ("feishu", "lark"):
            return "feishu"
        if brand == "google":
            if not data.get("refresh_token"):
                raise ProviderError(
                    "auth",
                    f"Google 个人连接的令牌文件没有 refresh_token：{credentials_file}。"
                    "请在设置里重新完成 Google 授权。",
                )
            return "google"
        raise ProviderError("invalid", f"个人连接需要 brand 字段（feishu / google）：{credentials_file}")
    if data.get("type") == "authorized_user" and data.get("refresh_token"):
        # Google's own user-token shape without our kind marker: a person's token
        # is a personal connection by construction.
        return "google"
    if data.get("type") == "service_account" and data.get("client_email"):
        return "google"
    if data.get("app_id") or data.get("app_secret"):
        return "feishu"
    raise ProviderError(
        "invalid",
        f"无法判断 {credentials_file} 属于哪个厂商："
        "Google 服务账号需 type=service_account，飞书应用需 app_id/app_secret。",
    )


def build_provider(credentials_file: str, *, agent_roster: tuple[str, ...] = ()) -> Any:
    """The factory a connection registry is given.

    Failures are raised rather than returning None: a connection whose provider cannot
    be built is a configuration error someone has to see, and a silent skip would show
    up much later as a document nobody is watching.
    """
    vendor = detect_vendor(credentials_file)
    if detect_kind(credentials_file) == "personal":
        if vendor == "google":
            from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import (
                GoogleDocsProvider,
            )

            return GoogleDocsProvider(credentials_file, identity="user")
        from jiuwenswarm.agents.harness.common.tools.clouddoc.feishu_provider import (
            FeishuDocsProvider,
        )

        data = _load(credentials_file)
        return FeishuDocsProvider(
            profile=str(data.get("profile") or ""),
            binary=str(data.get("lark_binary") or "lark-cli"),
            self_open_id=str(data.get("open_id") or ""),
            display_name=str(data.get("name") or ""),
            agent_roster=tuple(agent_roster),
            identity="user",
        )
    if vendor == "google":
        from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import (
            GoogleDocsProvider,
        )

        return GoogleDocsProvider(credentials_file)

    from jiuwenswarm.agents.harness.common.tools.clouddoc.feishu_provider import (
        FeishuDocsProvider,
    )

    with open(credentials_file, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # The roster of other agents' open_ids names the bots a mention must never treat
    # as a summoner. It is deployment policy, so the **host caller** passes it -- this
    # module stays host-free (the structure test pins that), and a host that passes
    # nothing gets the safe, unrostered default with the rate brake as backstop.
    return FeishuDocsProvider(
        profile=str(data.get("profile") or data.get("app_id") or ""),
        binary=str(data.get("lark_binary") or "lark-cli"),
        self_open_id=str(data.get("bot_open_id") or ""),
        agent_roster=tuple(agent_roster),
    )

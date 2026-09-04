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


def detect_vendor(credentials_file: str) -> str:
    """``"google"`` or ``"feishu"``, from the credential file's own shape."""
    try:
        with open(credentials_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ProviderError("invalid", f"无法读取凭证文件 {credentials_file}：{exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError("invalid", f"凭证文件不是对象：{credentials_file}")
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

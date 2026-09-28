"""Tokens, ids, roles, errors, settings and the shared JSON file."""

from __future__ import annotations

import asyncio
import json
import re
import time

import pytest

from jiuwenswarm.extensions.blackboard.common import tokens
from jiuwenswarm.extensions.blackboard.common.config import (
    HostSettings,
    host_settings_from,
    save_host_settings,
    validate_updates,
)
from jiuwenswarm.extensions.blackboard.common.errors import EXPIRED, INTERNAL, INVALID, UNAUTHORIZED, BlackboardError
from jiuwenswarm.extensions.blackboard.common.ids import new_id, new_ulid
from jiuwenswarm.extensions.blackboard.common.jsonstore import JsonStore
from jiuwenswarm.extensions.blackboard.common.roles import role_at_least, validate_role
from jiuwenswarm.extensions.blackboard.host.secrets import load_or_create


def test_member_tokens_and_invite_codes():
    token = tokens.new_member_token()
    assert token.startswith("bbm_") and len(token) > 40 and token != tokens.new_member_token()
    assert re.fullmatch(r"[0-9a-f]{64}", tokens.hash_token(token))
    assert tokens.hash_token(token) == tokens.hash_token(token)
    assert re.fullmatch(r"[a-z2-7]{20}", tokens.new_invite_code())


def test_document_tokens_round_trip_and_reject_tampering():
    token = tokens.mint_doc_token({"uid": "u_1", "ws": "ws_1", "doc": "d_1", "role": "editor"}, "secret")
    claims = tokens.verify_doc_token(token, "secret")
    assert claims["role"] == "editor" and claims["exp"] > time.time()

    header, payload, signature = token.split(".")
    forged = tokens._b64(json.dumps({"uid": "u_2", "exp": 9999999999}).encode())
    for bad in [
        f"{header}.{payload}.{signature[:-2]}AA",
        f"{header}.{forged}.{signature}",
        "not-a-token",
        "",
    ]:
        with pytest.raises(BlackboardError) as caught:
            tokens.verify_doc_token(bad, "secret")
        assert caught.value.code == UNAUTHORIZED
    with pytest.raises(BlackboardError):
        tokens.verify_doc_token(token, "another secret")

    old = tokens.mint_doc_token({"uid": "u_1"}, "secret", ttl_seconds=-5)
    with pytest.raises(BlackboardError) as caught:
        tokens.verify_doc_token(old, "secret")
    assert caught.value.code == EXPIRED


def test_ids_sort_by_time():
    first = new_ulid()
    time.sleep(0.002)
    second = new_ulid()
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", first)
    assert first < second
    assert new_id("ws").startswith("ws_")


def test_roles():
    assert role_at_least("owner", "editor") and role_at_least("viewer", "viewer")
    assert not role_at_least("commenter", "editor") and not role_at_least("admin", "viewer")
    assert validate_role("viewer") == "viewer"
    with pytest.raises(BlackboardError) as caught:
        validate_role("owner", ("editor", "viewer"))
    assert caught.value.code == INVALID and caught.value.details == {"field": "role"}


def test_errors_cross_the_wire_unchanged():
    error = BlackboardError("forbidden", "no", {"required": "owner"})
    back = BlackboardError.from_dict(error.to_dict())
    assert (back.code, back.message, back.details) == ("forbidden", "no", {"required": "owner"})
    odd = BlackboardError.from_dict("boom")
    assert (odd.code, odd.message) == (INTERNAL, "boom")
    assert BlackboardError.from_dict({"details": [1]}).details == {}


def test_host_settings_defaults_keep_the_host_private():
    settings = HostSettings()
    assert (settings.enabled, settings.bind, settings.port) == (False, "127.0.0.1", 19011)
    assert settings.base_url() == "http://127.0.0.1:19011"
    assert HostSettings(public_url="https://bb.example.com/").base_url() == "https://bb.example.com"


def test_settings_from_config_skip_broken_values():
    config = {"blackboard": {"host": {"enabled": "true", "port": "not a port", "public_url": "ftp://x", "bind": "0.0.0.0"}}}
    settings = host_settings_from(config)
    assert (settings.enabled, settings.port, settings.public_url, settings.bind) == (True, 19011, "", "0.0.0.0")
    assert host_settings_from({}) == HostSettings()
    assert host_settings_from({"blackboard": "junk"}) == HostSettings()


@pytest.mark.parametrize(
    "updates,field",
    [
        ({"port": 0}, "port"),
        ({"doc_port": "x"}, "doc_port"),
        ({"enabled": "maybe"}, "enabled"),
        ({"bind": "  "}, "bind"),
        ({"public_url": "bb.example.com"}, "public_url"),
        ({"doc_public_url": "https://bb.example.com"}, "doc_public_url"),
        ({"max_upload_mb": 0}, "max_upload_mb"),
        ({"name": "x" * 61}, "name"),
    ],
)
def test_bad_setting_values(updates, field):
    with pytest.raises(BlackboardError) as caught:
        validate_updates(updates)
    assert caught.value.code == INVALID and caught.value.details == {"field": field}


def test_the_blackboard_name_is_tidied():
    assert validate_updates({"name": "  Launch   team "}) == {"name": "Launch team"}
    assert validate_updates({"name": None}) == {"name": ""}


def test_settings_are_saved_under_blackboard_host():
    written = {}

    def update_config(mutate):  # noqa: ANN001
        data = {"models": {"default": "x"}, "blackboard": {"host": {"port": 19011, "note": "kept"}}}
        written.update(mutate(data))
        return written

    settings = save_host_settings({"enabled": "true", "port": "19020", "public_url": " https://bb.example.com "}, update_config)
    assert (settings.enabled, settings.port, settings.public_url) == (True, 19020, "https://bb.example.com")
    assert written["models"] == {"default": "x"}
    assert written["blackboard"]["host"] == {
        "port": 19020,
        "note": "kept",
        "enabled": True,
        "public_url": "https://bb.example.com",
    }
    with pytest.raises(BlackboardError):
        save_host_settings({"token": "x"}, update_config)


async def test_json_store_updates_do_not_lose_writes(tmp_path):
    store = JsonStore(tmp_path / "state.json", lambda: {"count": 0})
    assert store.read() == {"count": 0}

    def bump(data):  # noqa: ANN001
        data["count"] += 1
        return data["count"]

    results = await asyncio.gather(*(store.update(bump) for _ in range(20)))
    assert sorted(results) == list(range(1, 21))
    assert store.read() == {"count": 20}
    assert not list(tmp_path.glob("*.tmp"))

    (tmp_path / "state.json").write_text("[1, 2]", encoding="utf-8")
    assert store.read() == {"count": 0}


def test_host_secrets_are_made_once(tmp_path):
    path = tmp_path / "host" / "secrets.json"
    first = load_or_create(path)
    assert first.doc_secret and first.api_secret and first.doc_secret != first.api_secret
    assert load_or_create(path) == first
    path.write_text('{"doc_secret": "kept"}', encoding="utf-8")
    repaired = load_or_create(path)
    assert repaired.doc_secret == "kept" and repaired.api_secret

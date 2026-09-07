"""Google personal identity (matrix S.1, Google half): the OAuth user-token flow
and the provider's user-credential branch, with no OAuth client anywhere -- the
exchange is a fake, the redirect is a local socket, the token is made up.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse

import pytest

from jiuwenswarm.agents.harness.common.tools.clouddoc.factory import (
    build_provider,
    detect_kind,
    detect_vendor,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.google_oauth import (
    AUTH_URL,
    SCOPES,
    TOKEN_URL,
    LoopbackReceiver,
    authorized_user_info,
    build_auth_url,
    exchange_code,
    parse_code,
    write_authorized_user_file,
)
from jiuwenswarm.agents.harness.common.tools.clouddoc.google_provider import GoogleDocsProvider
from jiuwenswarm.agents.harness.common.tools.clouddoc.provider import AgentIdentity, ProviderError

CID, SECRET = "123.apps.googleusercontent.com", "shh"


def _token_file(tmp_path, **over):
    info = authorized_user_info(CID, SECRET, {"refresh_token": "1//rt"}, email="me@x.com", name="Me")
    info.update(over)
    f = tmp_path / "personal-google-me@x.com.json"
    write_authorized_user_file(f, info)
    return f


# ------------------------------------------------------------ the flow's pieces


def test_auth_url_asks_for_an_offline_refreshable_grant():
    url = build_auth_url(CID, "http://127.0.0.1:4242/", "st8")
    assert url.startswith(AUTH_URL + "?")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert q["client_id"] == [CID] and q["redirect_uri"] == ["http://127.0.0.1:4242/"]
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["state"] == ["st8"] and q["response_type"] == ["code"]
    assert set(q["scope"][0].split()) == set(SCOPES)
    with pytest.raises(ProviderError):
        build_auth_url("", "http://127.0.0.1:1/", "s")


def test_parse_code_takes_a_bare_code_or_the_redirected_url():
    assert parse_code("4/abc") == "4/abc"
    assert parse_code("http://127.0.0.1:4242/?state=st8&code=4%2Fxyz&scope=a", expected_state="st8") == "4/xyz"
    with pytest.raises(ProviderError):
        parse_code("http://127.0.0.1:4242/?state=other&code=4%2Fxyz", expected_state="st8")
    with pytest.raises(ProviderError):
        parse_code("http://127.0.0.1:4242/?state=st8&error=access_denied", expected_state="st8")
    with pytest.raises(ProviderError):
        parse_code("   ")


def test_exchange_code_posts_the_grant_and_insists_on_a_refresh_token():
    posted = []

    def fake_post(url, data):
        posted.append((url, data))
        return {"access_token": "at", "refresh_token": "1//rt", "expires_in": 3599}

    out = exchange_code(CID, SECRET, "4/abc", "http://127.0.0.1:4242/", post=fake_post)
    assert out["refresh_token"] == "1//rt"
    assert posted[0][0] == TOKEN_URL
    assert posted[0][1]["grant_type"] == "authorization_code" and posted[0][1]["code"] == "4/abc"
    with pytest.raises(ProviderError) as exc:
        exchange_code(CID, SECRET, "4/abc", "http://127.0.0.1:4242/", post=lambda u, d: {"access_token": "at"})
    assert "refresh_token" in str(exc.value)
    with pytest.raises(ProviderError):
        exchange_code(CID, SECRET, "bad", "http://127.0.0.1:4242/", post=lambda u, d: {"error": "invalid_grant"})
    with pytest.raises(ProviderError):
        exchange_code("", "", "4/abc", "http://127.0.0.1:4242/", post=fake_post)


def test_token_file_is_googles_authorized_user_shape_at_mode_0600(tmp_path):
    f = _token_file(tmp_path)
    assert oct(os.stat(f).st_mode & 0o777) == "0o600"
    info = json.loads(f.read_text())
    assert info["type"] == "authorized_user" and info["kind"] == "personal" and info["brand"] == "google"
    assert info["refresh_token"] == "1//rt" and info["client_id"] == CID and info["client_secret"] == SECRET
    assert info["email"] == "me@x.com"


@pytest.mark.asyncio
async def test_loopback_receiver_takes_exactly_the_expected_redirect():
    rx = LoopbackReceiver("st8")
    uri = await rx.start()
    assert uri.startswith("http://127.0.0.1:") and uri.endswith("/")

    async def get(path: str) -> str:
        reader, writer = await asyncio.open_connection("127.0.0.1", rx.port)
        writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        await writer.drain()
        data = await reader.read()
        writer.close()
        return data.decode("utf-8", "replace")

    waiter = asyncio.create_task(rx.wait(timeout=5))
    assert "404" in (await get("/?state=wrong&code=4%2Fno")).splitlines()[0]
    assert "200" in (await get("/?state=st8&error=access_denied")).splitlines()[0]
    assert not waiter.done(), "a foreign state or a denial does not settle the wait"
    assert "200" in (await get("/?state=st8&code=4%2Fyes")).splitlines()[0]
    assert await waiter == "4/yes"


@pytest.mark.asyncio
async def test_loopback_receiver_accepts_a_pasted_code_as_the_fallback():
    rx = LoopbackReceiver("st8")
    await rx.start()
    waiter = asyncio.create_task(rx.wait(timeout=5))
    await asyncio.sleep(0)
    rx.deliver("4/pasted")
    assert await waiter == "4/pasted"


# ------------------------------------------------------------ factory and provider


def test_a_google_token_file_builds_a_personal_provider(tmp_path):
    f = str(_token_file(tmp_path))
    assert detect_kind(f) == "personal" and detect_vendor(f) == "google"
    prov = build_provider(f)
    assert isinstance(prov, GoogleDocsProvider) and prov.personal is True
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"type": "authorized_user", "client_id": CID, "client_secret": SECRET, "refresh_token": "1//rt"}))
    assert detect_kind(str(bare)) == "personal", "Google's own shape is personal by construction"
    assert build_provider(str(bare)).personal is True


def test_a_token_file_without_a_refresh_token_is_refused_with_the_remedy(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"kind": "personal", "brand": "google", "type": "authorized_user", "client_id": CID}))
    with pytest.raises(ProviderError) as exc:
        detect_vendor(str(f))
    assert exc.value.kind == "auth" and "重新" in str(exc.value)


def test_user_credentials_refresh_from_the_token_file(tmp_path):
    from google.oauth2.credentials import Credentials

    prov = GoogleDocsProvider(str(_token_file(tmp_path)), identity="user")
    cred = prov._credentials()
    assert isinstance(cred, Credentials)
    assert cred.refresh_token == "1//rt" and cred.client_id == CID
    assert set(cred.scopes or ()) == set(SCOPES)
    svc = GoogleDocsProvider(str(tmp_path / "missing.json"))
    assert svc.personal is False
    with pytest.raises(ValueError):
        GoogleDocsProvider("x", identity="admin")


class _Drive:
    def __init__(self, user):
        self._user = user

    def about(self):
        d = self

        class About:
            def get(self, fields=""):
                class Exec:
                    def execute(self_):
                        return {"user": d._user}
                return Exec()
        return About()


@pytest.mark.asyncio
async def test_personal_identity_is_the_persons_email_from_drive(tmp_path, monkeypatch):
    prov = GoogleDocsProvider(str(_token_file(tmp_path)), identity="user")
    monkeypatch.setattr(prov, "_clients", lambda: (None, _Drive({"emailAddress": "Me@X.com", "displayName": "Me Person"})))
    ident = await prov.self_identity()
    assert ident == AgentIdentity(display_name="Me Person", address="Me@X.com")
    assert prov.identity_address == "Me@X.com"


@pytest.mark.asyncio
async def test_personal_identity_falls_back_to_the_file_when_drive_is_unreachable(tmp_path, monkeypatch):
    prov = GoogleDocsProvider(str(_token_file(tmp_path)), identity="user")

    def boom():
        raise ProviderError("transport", "offline")

    monkeypatch.setattr(prov, "_clients", boom)
    ident = await prov.self_identity()
    assert ident.address == "me@x.com" and ident.display_name == "Me"


@pytest.mark.asyncio
async def test_a_service_account_identity_still_comes_from_the_key(tmp_path):
    f = tmp_path / "sa.json"
    f.write_text(json.dumps({"type": "service_account", "client_email": "sa@p.iam.gserviceaccount.com"}))
    prov = GoogleDocsProvider(str(f))
    assert (await prov.self_identity()).address == "sa@p.iam.gserviceaccount.com"
    assert prov.personal is False


def test_under_a_personal_identity_self_is_the_person_and_not_a_service_account(tmp_path):
    """``author.me`` is the platform's own "this is the token's user"; the
    service-account test is about *other* agents and must not fire on the person."""
    prov = GoogleDocsProvider(str(_token_file(tmp_path)), identity="user")
    assert prov._is_service_account("Me Person") is False
    assert prov._is_service_account("me@x.com") is False
    assert prov._is_service_account("sa@p.iam.gserviceaccount.com") is True

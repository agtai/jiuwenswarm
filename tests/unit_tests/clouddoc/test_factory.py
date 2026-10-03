"""The provider factory: the vendor is read from the credentials, never declared.

Moved from the Feishu provider tests; they build a provider from a key file, which
is the factory's job.
"""
from __future__ import annotations

import json

import pytest

from jiuwenswarm.clouddoc.providers.base import ProviderError


def test_the_vendor_is_read_from_the_credentials_not_declared(tmp_path):
    """The file decides, because the file is what the calls actually run on. A vendor
    field in config could disagree with it, and then one of the two is a lie."""
    from jiuwenswarm.clouddoc.providers.factory import detect_vendor

    g = tmp_path / "g.json"
    g.write_text(json.dumps({"type": "service_account", "client_email": "a@b.iam"}))
    assert detect_vendor(str(g)) == "google"

    f = tmp_path / "f.json"
    f.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s"}))
    assert detect_vendor(str(f)) == "feishu"


def test_an_unrecognisable_credential_is_a_configuration_error(tmp_path):
    """Raised rather than defaulted: guessing a vendor produces calls that fail much
    later, with nothing pointing back at the file."""
    from jiuwenswarm.clouddoc.providers.factory import detect_vendor

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"hello": "world"}))
    with pytest.raises(ProviderError):
        detect_vendor(str(bad))

    missing = tmp_path / "nope.json"
    with pytest.raises(ProviderError):
        detect_vendor(str(missing))


def test_a_feishu_credential_builds_a_feishu_provider(tmp_path):
    from jiuwenswarm.clouddoc.providers.factory import build_provider

    f = tmp_path / "f.json"
    f.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s", "bot_open_id": "ou_b"}))
    prov = build_provider(str(f))
    assert prov.kind == "feishu"
    assert prov._is_self("ou_b") is True


def test_credential_address_reads_either_vendors_identity(tmp_path):
    from jiuwenswarm.clouddoc.providers.factory import credential_address

    g = tmp_path / "g.json"
    g.write_text(json.dumps({"type": "service_account", "client_email": "a@b.iam"}))
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s", "bot_open_id": " ou_bot "}))
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"app_id": "cli_x", "app_secret": "s"}))
    assert credential_address(str(g)) == "a@b.iam"
    assert credential_address(str(f)) == "ou_bot"
    assert credential_address(str(bare)) == ""
    assert credential_address(str(tmp_path / "missing.json")) == ""
    assert credential_address("") == ""

"""Redaction performance must not weaken message or exception masking."""
import logging

import pytest

from jiuwenswarm.common import utils


def test_handlers_do_not_rescan_unchanged_sanitized_record(monkeypatch):
    record = logging.LogRecord("probe", logging.INFO, __file__, 1, "private_token='secret-value'", (), None)
    sanitize = utils._sanitize_log_text
    seen = []
    def counted(text):
        seen.append(text)
        return sanitize(text)
    monkeypatch.setattr(utils, "_sanitize_log_text", counted)
    for _ in range(6):
        assert utils.SensitiveDataFilter().filter(record)
    assert "secret-value" not in record.getMessage()
    assert len(seen) == 1
    record.msg = "api_key=%s"
    record.args = ("new-secret",)
    assert utils.SensitiveDataFilter().filter(record)
    assert "new-secret" not in record.getMessage()
    assert len(seen) == 2
    record.exc_text = "failure: password='exception-secret'"
    for _ in range(6):
        assert utils.SensitiveDataFilter().filter(record)
    assert "exception-secret" not in record.exc_text
    assert len(seen) == 3


@pytest.mark.parametrize("key", ["private_token", "CAT_CAFE_CALLBACK_TOKEN", "my_private_key",
    "TOKEN", "prefix.api-key", "prefix-user_id", "a" * 160 + "secret"])
@pytest.mark.parametrize("quote", ["'", '"', ""])
def test_sensitive_key_boundaries_retain_existing_masking(key, quote):
    text = f"{quote}{key}{quote}: 'sample-sensitive-value'"
    assert "sample-sensitive-value" not in utils.mask_sensitive(text)

"""Per-call capability selection; no Provider call or saved config mutation."""

from copy import deepcopy

import pytest

from jiuwenswarm.common.reasoning_injector import bounded_semantic_request_options


@pytest.mark.parametrize(
    "base,provider,model,expected",
    [
        (
            "https://api.deepseek.com",
            "DeepSeek",
            "deepseek-v4-flash",
            {"extra_body": {"thinking": {"type": "disabled"}}},
        ),
        (
            "https://api.deepseek.com/v1",
            "OpenAI",
            "deepseek-v4-pro",
            {"extra_body": {"thinking": {"type": "disabled"}}},
        ),
        ("https://other.invalid", "DeepSeek", "deepseek-v4-flash", {}),
        ("https://api.deepseek.com", "DeepSeek", "future-unverified-model", {}),
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "OpenAI",
            "deepseek-v4-flash",
            {},
        ),
        ("https://api.openai.com/v1", "OpenAI", "unverified-model", {}),
    ],
)
def test_semantic_reasoning_is_capability_bound_and_does_not_change_configuration(
    base, provider, model, expected
):
    config = {
        "api_base": base,
        "client_provider": provider,
        "model_name": model,
        "api_key": "private-canary",
    }
    before = deepcopy(config)
    actual = bounded_semantic_request_options(config)
    assert actual == expected and config == before
    assert "private-canary" not in str(actual)
    actual["untrusted"] = True
    assert bounded_semantic_request_options(config) == expected


def test_bounded_options_preserve_unrelated_provider_options_without_mutating_them():
    client = {"api_base": "https://api.deepseek.com", "client_provider": "DeepSeek", "model_name": "deepseek-v4-flash"}
    request = {"extra_body": {"thinking": {"type": "enabled"}, "provider_option": "keep"}}
    original = deepcopy(request)
    options = bounded_semantic_request_options(client, request)
    assert options == {"extra_body": {"thinking": {"type": "disabled"}, "provider_option": "keep"}}
    assert request == original

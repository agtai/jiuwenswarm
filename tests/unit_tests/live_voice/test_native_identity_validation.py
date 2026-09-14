"""Carrier and runtime identities use the existing contract's accepted values."""

import pytest

from jiuwenswarm.channels.live_voice import native_interaction_carrier as carrier
from jiuwenswarm.channels.live_voice import native_interaction_runtime as runtime
from jiuwenswarm.common.schema import native_interaction_contract as contract


class StringSubclass(str):
    pass


@pytest.mark.parametrize("module,error_type,reason", [
    (carrier, carrier.NativeCarrierViolation, "NATIVE_CARRIER_IDENTITY_INVALID"),
    (runtime, runtime.NativeInteractionRuntimeError, "NATIVE_RUNTIME_IDENTITY_INVALID"),
])
def test_identity_accepted_values_and_domain_rejections(module, error_type, reason):
    for value in ("id", "a" * 256, "😀" * 256, "项目-id", "inside space"):
        assert module._identity(value, "field") == contract._identity(value, "field") == value
    for value in (None, 1, True, b"id", "", " ", " id", "id\n", "a\x00b", "a\u200bb",
                  "a\u2028b", "a\u2029b", "\ud800", "a" * 257, "😀" * 257, StringSubclass("id")):
        with pytest.raises(contract.NativeInteractionContractViolation):
            contract._identity(value, "field")
        with pytest.raises(error_type) as caught:
            module._identity(value, "field")
        assert type(caught.value) is error_type
        assert caught.value.reason == reason
        assert str(caught.value) == "field must be a bounded canonical identity"
        assert caught.value.__cause__ is None
        if module is carrier:
            assert caught.value.code is carrier.ErrorCode.INVALID_ARGUMENT

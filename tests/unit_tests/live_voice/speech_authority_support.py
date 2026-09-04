"""Explicit test Media/Runtime issuer for streaming port consumer tests.

This supplies the local authority formerly implicit in these fixtures. Production
issuance is separately tested through DedicatedMediaProductRegistry.
"""

from dataclasses import replace
import threading

import pytest

from jiuwenswarm.server.live_voice.streaming_speech import (
    CaptureRef,
    RecognitionStreamRef,
    RecognitionStreamRequest,
    RecognitionTurnDetection,
    SynthesisStreamRequest,
    SpeechResponseAuthority,
    authorize_stream_request,
)

_lock = threading.RLock()
_requests = {}
_responses = {}
_current = {}


@pytest.fixture(autouse=True)
def speech_test_issuer():
    reset_test_issuer()
    yield
    reset_test_issuer()


def reset_test_issuer():
    _requests.clear()
    _responses.clear()
    _current.clear()


def response_authority(response, *, activate=True):
    if isinstance(response, SpeechResponseAuthority):
        return response
    with _lock:
        prior = _current.get(response.interaction_id)
        if activate and (
            prior is None or response.response_generation > prior.response_generation
        ):
            _current[response.interaction_id] = response
        if response not in _responses:
            _responses[response] = SpeechResponseAuthority(
                response,
                lambda: _current.get(response.interaction_id, response) == response,
            )
        return _responses[response]


def authorized_request(request):
    if isinstance(request, RecognitionStreamRef):
        request = RecognitionStreamRequest(request, RecognitionTurnDetection.manual())
    if not isinstance(request, (RecognitionStreamRequest, SynthesisStreamRequest)):
        return request  # malformed-input tests still exercise the real validator
    if request.authority is not None:
        return request
    with _lock:
        if isinstance(request, SynthesisStreamRequest):
            request = replace(
                request, response_authority=response_authority(request.ref.response)
            )
        prior = _requests.get(request.ref)
        if prior is None:
            prior = authorize_stream_request(request, is_current=lambda: True)
            _requests[request.ref] = prior
        return replace(request, authority=prior.authority)


async def begin_recognition(owner, binding, **kwargs):
    detection = kwargs.get("turn_detection") or RecognitionTurnDetection.manual()
    ref = RecognitionStreamRef(
        binding.media_session_id,
        binding.generation.value,
        CaptureRef(
            binding.generation.id,
            binding.generation.value,
            binding.frame_format.sample_rate_hz,
        ),
    )
    return await owner.begin(
        binding,
        **kwargs,
        request=authorized_request(RecognitionStreamRequest(ref, detection)),
    )

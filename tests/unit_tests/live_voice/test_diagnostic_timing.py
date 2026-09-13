"""Endpoint semantics and evidence isolation, without Provider/device claims."""
import hashlib
import json
import wave

import pytest

from scripts.live_voice.diagnostic_timing import attach_recording_annotations, response_timings
from scripts.live_voice.analyze_demo_profile import sanitize_record


def observations():
    rows = []
    def add(event, ms, clock="browser", **fields):
        rows.append({"event": event, "monotonic_ms": ms, "clock_id": clock, "sequence": len(rows),
                     "fields": {"interaction_id": "i", **fields}})
    def native(ms, milestone, **fields):
        add("native_business_timeline", ms, "gateway", milestone=milestone, activation_id="a",
            session_id="s", **fields)
    native(2000, "endpoint_observed", provider_item_id="item", provider_end_ms=800)
    native(2001, "input_committed", provider_item_id="item", turn_id="t", provider_start_ms=200, provider_end_ms=800)
    native(2002, "response_sent", response_request_id="req")
    native(2050, "response_created", provider_response_id="provider", response_request_id="req", response_kind="direct")
    native(2700, "provider_first_audio", provider_response_id="provider", response_id="r", response_generation=1, turn_id="t")
    add("p1_end_of_turn", 1000, provider_start_ms=200, provider_end_ms=800,
        input_tail_estimate_ms=500, input_tail_low_estimate_ms=510, capture_callback_ms=990)
    for event, ms in (("playout_pcm_accepted", 1800), ("playout_first_scheduled", 1860),
                       ("playout_clock_reached_start", 1900), ("playout_signal_scheduled", 1861)):
        add(event, ms, response_id="r", response_generation=1,
            output_estimate_ms=1920, output_time_method="get_output_timestamp_estimate")
    return rows


def test_same_response_local_clock_components_and_nested_estimates():
    result, = response_timings(observations())
    assert result["stages_ms"]["E_created_to_first_audio"] == 650
    assert result["stages_ms"]["D_to_G_browser_eot_to_render_poll"] == 900
    assert result["stages_ms"]["G_pcm_to_schedule"] == 60
    assert result["software_estimates"]["processed_energy_tail_to_output_device_ms"] == 1420
    assert result["physical"] == {"state": "unmeasured", "duration_ms": None}


@pytest.mark.parametrize("change", ["clock", "generation", "duplicate_eot", "notification", "legacy", "noise", "stop", "pause", "null_capture"])
def test_missing_ambiguous_wrong_scope_and_interrupted_endpoints_never_become_physical(change):
    rows = observations()
    if change == "clock": rows[-1]["clock_id"] = "other-tab"
    if change == "generation": rows[-1]["fields"]["response_generation"] = 2
    if change == "duplicate_eot": rows.append(dict(rows[5]))
    if change == "notification": rows[3]["fields"]["response_kind"] = "work_notification"
    if change == "legacy": rows[1]["fields"].pop("provider_start_ms")
    if change == "noise": rows[5]["fields"]["input_tail_low_estimate_ms"] = 999
    if change == "stop": rows.append({**rows[-1], "event": "playout_stop_requested", "monotonic_ms": 1901})
    if change == "pause": rows.append({**rows[-1], "event": "playout_tentative_paused", "monotonic_ms": 1901})
    if change == "null_capture": rows[5]["fields"]["capture_callback_ms"] = None
    result = response_timings(rows)[0]
    assert result["software_estimates"]["processed_energy_tail_to_output_device_ms"] is None
    assert result["physical"]["duration_ms"] is None
    if change in {"duplicate_eot", "notification", "legacy"}:
        assert result["stages_ms"]["D_to_G_browser_eot_to_render_poll"] is None


def manifest(tmp_path):
    wav = tmp_path / "recording.wav"
    with wave.open(str(wav), "wb") as stream:
        stream.setparams((1, 2, 48000, 48000, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 48000)
    # Synthetic file verifies arithmetic only, never product acoustic acceptance.
    value = {"format": "live-voice.recording-annotations.v1", "recording_path": wav.name,
        "sha256": hashlib.sha256(wav.read_bytes()).hexdigest(), "sample_rate_hz": 48000,
        "recording_kind": "acoustic", "annotations": [{"session_id": "s", "interaction_id": "i",
        "response_id": "r", "response_generation": 1, "user_end_sample": 4800, "headphone_start_sample": 24000,
        "user_channel": 0, "headphone_channel": 0, "annotation_uncertainty_ms": 5,
        "annotation_method": "manual_waveform_and_listening", "differential_delay_ms": 2,
        "differential_delay_uncertainty_ms": 1}]}
    path = tmp_path / "annotations.json"
    return path, value


def test_acoustic_sample_clock_interval_and_explicit_channel_correction(tmp_path):
    path, value = manifest(tmp_path)
    path.write_text(json.dumps(value))
    result = response_timings(observations())
    attach_recording_annotations(result, path)
    assert result[0]["physical"]["recorder_interval_ms"] == 400
    assert result[0]["physical"]["duration_ms"] == 398
    for kind, correction in (("digital_loopback", 2), ("acoustic", None)):
        value["recording_kind"] = kind
        value["annotations"][0]["differential_delay_ms"] = correction
        path.write_text(json.dumps(value))
        attach_recording_annotations(result, path)
        assert result[0]["physical"]["duration_ms"] is None


@pytest.mark.parametrize("bad", ["hash", "rate", "identity", "order", "channel", "uncertainty", "duplicate"])
def test_bad_recording_evidence_cannot_partially_attach_a_physical_result(tmp_path, bad):
    path, value = manifest(tmp_path)
    if bad == "hash": value["sha256"] = "bad"
    if bad == "rate": value["sample_rate_hz"] = 24000
    if bad == "identity": value["annotations"][0]["response_id"] = "other"
    if bad == "order": value["annotations"][0]["headphone_start_sample"] = 1
    if bad == "channel": value["annotations"][0]["headphone_channel"] = 1
    if bad == "uncertainty": value["annotations"][0]["annotation_uncertainty_ms"] = -1
    if bad == "duplicate": value["annotations"] *= 2
    path.write_text(json.dumps(value))
    result = response_timings(observations())
    with pytest.raises(ValueError): attach_recording_annotations(result, path)
    assert result[0]["physical"]["duration_ms"] is None


def test_offline_new_timing_fields_are_scalar_only():
    row = {"event": "playout_signal_scheduled", "observed_at": "2026-09-09T12:00:00Z",
        "monotonic_ms": 10, "fields": {"output_estimate_ms": 20, "acoustic_measured": False,
        "output_time_method": "get_output_timestamp_estimate", "pcm": "PRIVATE", "transcript": "PRIVATE"}}
    clean = sanitize_record(row)
    assert clean["fields"]["output_estimate_ms"] == 20
    assert "PRIVATE" not in repr(clean)

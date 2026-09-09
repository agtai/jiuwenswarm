"""Identity-bound timing views. No nearest-turn joins or cross-clock durations."""
from __future__ import annotations

import hashlib
import json
import math
import wave
from collections import defaultdict
from pathlib import Path


def number(value):
    return type(value) in {int, float} and math.isfinite(value)


def unique(rows):
    return rows[0] if len(rows) == 1 else None


def difference(start, end):
    if not start or not end or not start.get("clock_id") or start["clock_id"] != end.get("clock_id"):
        return None
    duration = end["monotonic_ms"] - start["monotonic_ms"]
    return round(duration, 3) if duration >= 0 else None


def response_timings(records):
    """Separate browser/Gateway views; an absent or ambiguous boundary stays null."""
    browser, by_response, first_audio, native_index, eots, receives = (defaultdict(list) for _ in range(6))
    for row in records:
        f = row["fields"]
        key = (row.get("clock_id"), f.get("interaction_id"), f.get("response_id"), f.get("response_generation"))
        response_key = key[1:]
        by_response[response_key].append(row)
        if row["event"].startswith("playout_") and all(v is not None for v in key) and type(key[3]) is int:
            browser[key].append(row)
        if row["event"] == "p1_end_of_turn":
            eots[(key[0], key[1], f.get("provider_start_ms"), f.get("provider_end_ms"))].append(row)
        if row["event"] == "media_downlink_received":
            receives[(key[0], f.get("media_session_id"), f.get("seq"))].append(row)
        if row["event"] == "native_business_timeline":
            if f.get("milestone") == "provider_first_audio":
                first_audio[response_key].append(row)
            for field in ("provider_response_id", "response_request_id", "turn_id", "provider_item_id"):
                if f.get(field) is not None:
                    native_index[(key[0], key[1], f.get("activation_id"), f.get("milestone"), field, f[field])].append(row)
    results = []
    for (clock, interaction, response_id, generation), rows in browser.items():
        rows.sort(key=lambda r: r["monotonic_ms"])
        def first(event):
            return next((r for r in rows if r["event"] == event), None)

        pcm = first("playout_pcm_accepted")
        scheduled = first("playout_first_scheduled")
        polled = first("playout_clock_reached_start")
        signal = first("playout_signal_scheduled")
        stopped = first("playout_stop_requested")
        paused = first("playout_tentative_paused")
        audio = unique(first_audio[(interaction, response_id, generation)])
        origin = audio["fields"] if audio else {}
        def native_match(milestones, **fields):
            if audio is None or any(v is None for v in fields.values()):
                return None
            field, value = next(iter(fields.items()))
            return unique([r for milestone in milestones for r in native_index[
                (audio["clock_id"], interaction, origin.get("activation_id"), milestone, field, value)]
                if all(r["fields"].get(k) == v for k, v in fields.items())])

        created = native_match({"response_created", "continuation_created_unadmitted"},
                               provider_response_id=origin.get("provider_response_id"))
        cf = created["fields"] if created else {}
        sent = native_match({"response_sent"}, response_request_id=cf.get("response_request_id"))
        commit = native_match({"input_committed"}, turn_id=origin.get("turn_id"))
        commit_fields = commit["fields"] if commit else {}
        endpoint = native_match({"endpoint_observed"}, provider_item_id=commit_fields.get("provider_item_id"))
        response_rows = by_response[(interaction, response_id, generation)]
        def first_frame(event, stage):
            return unique([r for r in response_rows if audio and r["clock_id"] == audio["clock_id"]
                           and r["event"] == event and r["fields"].get("stage") == stage
                           and r["fields"].get("frame_seq") == 0])
        admission = first_frame("native_audio_supply", "gateway_runtime_admission")
        source = first_frame("media_downlink_frame", "source_ready")
        downlink = first_frame("media_downlink_frame", "sent")
        media = downlink["fields"].get("media_session_id") if downlink else None
        receive = unique(receives[(clock, media, 0)]) if media else None
        callback = ({**receive, "monotonic_ms": receive["fields"]["message_callback_ms"]}
                    if receive and number(receive["fields"].get("message_callback_ms")) else None)
        eot = None
        if cf.get("response_kind") == "direct" and commit is not None:
            # Input bounds plus interaction must identify exactly one browser EOT.
            # Reconnect/reused bounds or legacy missing links do not justify a guess.
            if all(number(commit_fields.get(k)) for k in ("provider_start_ms", "provider_end_ms")):
                eot = unique(eots[(clock, interaction, commit_fields["provider_start_ms"], commit_fields["provider_end_ms"])])
        result = {"session_id": origin.get("session_id"), "interaction_id": interaction,
            "response_id": response_id, "response_generation": generation, "turn_id": origin.get("turn_id"),
            "response_kind": cf.get("response_kind", "legacy_unknown"), "browser_clock_id": clock,
            "gateway_clock_id": audio["clock_id"] if audio else None,
            "state": "interrupted" if stopped else "render_observed" if polled else "not_render_observed",
            "physical": {"state": "unmeasured", "duration_ms": None},
            "stages_ms": {
                "AB_physical_input_to_browser": None,
                "BC_browser_to_gateway_one_way": None,
                "CD_last_input_to_endpoint": None,
                "D_endpoint_to_request_sent": difference(endpoint, sent) if eot else None,
                "DE_request_sent_to_created": difference(sent, created),
                "E_created_to_first_audio": difference(created, audio),
                "EF_first_audio_to_admission_end": difference(audio, admission),
                "F_admission_end_to_first_downlink": difference(admission, downlink),
                "F_source_ready_to_first_downlink": difference(source, downlink),
                "FG_gateway_to_browser_one_way": None,
                "G_callback_to_pcm_accept": difference(callback, pcm),
                "D_to_G_browser_eot_to_pcm": difference(eot, pcm),
                "G_pcm_to_schedule": difference(pcm, scheduled),
                "G_schedule_to_render_poll": difference(scheduled, polled),
                "D_to_G_browser_eot_to_render_poll": difference(eot, polled),
            }}
        sf = signal["fields"] if signal else {}
        pf = polled["fields"] if polled else {}
        ef = eot["fields"] if eot else {}
        output = sf.get("output_estimate_ms")
        # Scheduling a signal does not prove it survived STOP or reached the device.
        valid_output = (signal is not None and polled is not None and number(output)
                        and sf.get("output_time_method") == "get_output_timestamp_estimate"
                        and (stopped is None or stopped["monotonic_ms"] > output)
                        and (paused is None or paused["monotonic_ms"] > output))
        tail, low_tail = ef.get("input_tail_estimate_ms"), ef.get("input_tail_low_estimate_ms")
        capture_callback = ef.get("capture_callback_ms")
        valid_tail = (eot is not None and number(tail) and number(low_tail)
                      and 0 <= eot["monotonic_ms"] - tail <= 5000
                      and abs(tail - low_tail) <= 100
                      and number(capture_callback)
                      and 0 <= eot["monotonic_ms"] - capture_callback <= 250)
        # Eligibility limits are diagnostic screening, not an accuracy bound.
        result["software_estimates"] = {
            "input_method": ef.get("input_time_method", "unavailable"),
            "output_method": sf.get("output_time_method", "unavailable"),
            "input_tail_to_eot_ms": round(eot["monotonic_ms"] - tail, 3) if valid_tail else None,
            "eot_to_output_device_ms": round(output - eot["monotonic_ms"], 3)
                if valid_output and eot and output >= eot["monotonic_ms"] else None,
            "processed_energy_tail_to_output_device_ms": round(output - tail, 3)
                if valid_output and valid_tail and output >= tail else None,
            "poll_render_overshoot_ms": pf.get("render_clock_overshoot_ms"),
            "signal_offset_in_first_signal_source_ms": sf.get("signal_offset_ms"),
            "acoustic_measured": False,
            "eligibility_is_accuracy_bound": False,
        }
        result["evidence"] = {name: {"clock_id": row["clock_id"], "sequence": row.get("sequence"),
                                    "monotonic_ms": row["monotonic_ms"]} if row else None
            for name, row in {"eot": eot, "pcm": pcm, "scheduled": scheduled, "render_poll": polled,
                              "signal": signal, "endpoint": endpoint, "sent": sent,
                              "created": created, "provider_first_audio": audio, "admission_end": admission,
                              "downlink": downlink, "message_callback": callback}.items()}
        results.append(result)
    return results


def attach_recording_annotations(responses, path):
    """Read explicitly annotated local PCM WAV evidence; never infer speech from energy.

    The measured boundary is at the recorder microphone. Unknown differential
    propagation/channel delay prevents a corrected mouth-to-headphone value.
    """
    path = Path(path)
    if path.stat().st_size > 1_000_000:
        raise ValueError("Acoustic annotation manifest exceeds 1 MiB")
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or manifest.get("format") != "live-voice.recording-annotations.v1":
        raise ValueError("Unsupported recording annotation format")
    recording = (path.parent / manifest["recording_path"]).resolve()
    with recording.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != manifest.get("sha256"):
        raise ValueError("Recording SHA-256 mismatch")
    with wave.open(str(recording), "rb") as wav:
        rate, frames, channels = wav.getframerate(), wav.getnframes(), wav.getnchannels()
    if rate != manifest.get("sample_rate_hz") or rate <= 0:
        raise ValueError("Recording sample rate mismatch")
    kind = manifest.get("recording_kind")
    if kind not in {"acoustic", "digital_loopback"}:
        raise ValueError("Recording boundary must be explicit")
    annotations = manifest.get("annotations")
    if not isinstance(annotations, list) or not 1 <= len(annotations) <= 100:
        raise ValueError("Expected 1 to 100 annotated turns")
    pending, seen = [], set()
    keys = ("session_id", "interaction_id", "response_id", "response_generation")
    for entry in annotations:
        if not isinstance(entry, dict) or any(entry.get(k) is None for k in keys):
            raise ValueError("Annotation requires complete response identity")
        key = tuple(entry[k] for k in keys)
        matches = [r for r in responses if tuple(r.get(k) for k in keys) == key]
        if len(matches) != 1 or key in seen:
            raise ValueError("Recording response identity is ambiguous, absent or duplicated")
        seen.add(key)
        start, end = entry.get("user_end_sample"), entry.get("headphone_start_sample")
        if type(start) is not int or type(end) is not int or not 0 <= start <= end < frames:
            raise ValueError("Annotated sample order or bounds invalid")
        for name in ("user_channel", "headphone_channel"):
            if type(entry.get(name)) is not int or not 0 <= entry[name] < channels:
                raise ValueError("Annotated channel is outside recording")
        uncertainty = entry.get("annotation_uncertainty_ms")
        if not number(uncertainty) or uncertainty < 0 or entry.get("annotation_method") != "manual_waveform_and_listening":
            raise ValueError("Manual annotation method and uncertainty required")
        correction = entry.get("differential_delay_ms")
        correction_uncertainty = entry.get("differential_delay_uncertainty_ms")
        if correction is not None and (not number(correction) or not number(correction_uncertainty)
                                      or correction_uncertainty < 0):
            raise ValueError("Differential propagation/channel correction requires uncertainty")
        recorded = (end - start) * 1000 / rate
        corrected = recorded - correction if correction is not None and kind == "acoustic" else None
        if corrected is not None and corrected < 0:
            raise ValueError("Corrected physical duration cannot be negative")
        pending.append((matches[0], {"state": "annotated_acoustic" if kind == "acoustic" else "digital_only",
            "duration_ms": corrected, "recorder_interval_ms": recorded,
            "annotation_uncertainty_ms": uncertainty,
            "differential_delay_ms": correction, "differential_delay_uncertainty_ms": correction_uncertainty,
            "recording_sha256": digest, "sample_rate_hz": rate,
            "user_end_sample": start, "headphone_start_sample": end,
            "user_channel": entry["user_channel"], "headphone_channel": entry["headphone_channel"],
            "annotation_method": entry["annotation_method"],
            "sample_clock_calibration": "nominal_rate_not_independently_calibrated"}))
    # Validate the entire import before attaching any result.
    for response, evidence in pending:
        response["physical"] = evidence

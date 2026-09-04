# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Browser-free speech-end-to-first-audio baseline over the real formal route.

Plays synthesized zh-CN utterances into the dedicated media uplink at real
20 ms pacing, lets the server VAD commit the turn, submits the recognised
final through ``live_voice.composition.unified.submit`` exactly as the browser
does (the gateway injects auth, voice claim and interaction engine), waits for
the authoritative ``chat.final`` presentation, requests authoritative synthesis
and opens the downlink to observe the first audio frame.

Every timestamp is the driver's own wall clock. "speech_end" is the moment the
last NON-silent frame was sent, i.e. the user's last word; the appended silence
is what lets the server VAD fire. Raw audio and transcripts are kept only in
the process; the JSONL retains counts and timings.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import statistics
import struct
import sys
import time
import uuid
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import websockets  # noqa: E402

WS_URL = "ws://127.0.0.1:19000/ws"
MEDIA_BASE = "ws://127.0.0.1:19000"
ORIGIN = "http://localhost:5173"
MEDIA_SUBPROTOCOL = "live-voice.media.v1"
MEDIA_AUTH_CONTRACT = "live-voice.media-auth.v1"
MEDIA_CONTRACT = "live-voice.media.v1"
EOT_CAPABILITY = "media.end_of_turn.v1"
SPEECH_CONTRACT = "live-voice.contract.v2"
SAMPLE_RATE = 48_000
FRAME_SAMPLES = SAMPLE_RATE // 50  # 20 ms
LOCALE = "zh-CN"
NOTIFICATION_BATCH = 16
TRAILING_SILENCE_SECONDS = 2.0
WIRE_HEADER = struct.Struct("<4sBBHQQQI")
PROJECT_ID = "proj_2b0bce69"
PROJECT_DIR = r"C:\Users\hongx\AppData\Local\Temp\p3-9-terminal-notify-89ed2dad"
MODEL_NAME = "deepseek-v4-flash"

SCENARIOS: dict[str, dict[str, str]] = {
    "short": {
        "text": "请用一句话告诉我，你是谁。",
        "expect": "<=200 chars, no tool -> only per-turn semantic call",
    },
    "medium": {
        "text": "请用大约二百五十字介绍一下机器学习的基本概念。",
        "expect": ">200 chars -> spoken revision (length trigger)",
    },
    "long": {
        "text": "请详细介绍人工智能的发展历史，分成五个阶段，每个阶段都说明代表性成果。",
        "expect": "long answer -> spoken revision, may hit 12s timeout",
    },
    "tool": {
        "text": "请运行 git status 命令，告诉我当前项目的状态。",
        "expect": "tool result -> spoken revision (tool trigger)",
    },
    "task": {
        # One distinct request per round: the delegation review refuses a
        # repeated request as a duplicate and answers it as a foreground
        # dialogue turn, and a task that writes into the project dirties the
        # worktree so the next creation is rejected. Read-only analyses keep
        # every round a genuine creation turn.
        "text": "帮我创建一个后台任务，统计这个项目里一共有多少个 Python 文件。",
        "texts": [
            "帮我创建一个后台任务，统计这个项目里一共有多少个 Python 文件。",
            "帮我创建一个后台任务，找出这个项目里最大的三个文件并告诉我文件名。",
            "帮我创建一个后台任务，数一数这个项目的 README 有多少行。",
            "帮我创建一个后台任务，列出这个项目里所有的 Markdown 文件名。",
            "帮我创建一个后台任务，统计 scripts 目录下一共有多少个文件。",
        ],
        "expect": "task.create each round -> semantic resolution (+ any delegation review) before the spoken confirmation",
    },
}


def _header_kwarg() -> str:
    params = inspect.signature(websockets.connect).parameters
    return "additional_headers" if "additional_headers" in params else "extra_headers"


def _now_ms() -> float:
    return time.time() * 1000.0


def _wav_to_frames(audio_wav: bytes) -> tuple[list[tuple[float, ...]], int]:
    """Decode PCM16 mono WAV, upsample to 48 kHz, split into 20 ms frames.

    Returns the frames and the index of the last non-silent frame.
    """
    import io

    with wave.open(io.BytesIO(audio_wav), "rb") as source:
        rate = source.getframerate()
        channels = source.getnchannels()
        raw = source.readframes(source.getnframes())
    count = len(raw) // 2
    signed = struct.unpack(f"<{count}h", raw)
    if channels != 1:
        signed = signed[::channels]
    mono = [value / 32768.0 for value in signed]
    if rate != SAMPLE_RATE:
        ratio = SAMPLE_RATE / rate
        length = int(len(mono) * ratio)
        resampled = []
        for index in range(length):
            position = index / ratio
            low = int(position)
            high = min(low + 1, len(mono) - 1)
            weight = position - low
            resampled.append(mono[low] * (1.0 - weight) + mono[high] * weight)
        mono = resampled
    frames: list[tuple[float, ...]] = []
    last_speech = -1
    for start in range(0, len(mono), FRAME_SAMPLES):
        block = mono[start : start + FRAME_SAMPLES]
        if len(block) < FRAME_SAMPLES:
            block = block + [0.0] * (FRAME_SAMPLES - len(block))
        if max(abs(v) for v in block) > 0.01:
            last_speech = len(frames)
        frames.append(tuple(block))
    silence = tuple([0.0] * FRAME_SAMPLES)
    frames.extend([silence] * int(TRAILING_SILENCE_SECONDS * 50))
    return frames, last_speech


def _encode(lease: str, generation: int, seq: int, cursor: int, samples: tuple[float, ...]) -> bytes:
    raw_lease = lease.encode("utf-8")
    payload = struct.pack(f"<{len(samples)}f", *samples)
    return (
        WIRE_HEADER.pack(b"LVM1", 1, 1, len(raw_lease), generation, seq, cursor, len(payload))
        + raw_lease
        + payload
    )


async def synthesize_fixtures(texts: dict[str, str]) -> dict[str, bytes]:
    os.environ.setdefault("LIVE_VOICE_SPEECH_PROVIDER", "openai")
    os.environ.setdefault("LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED", "1")
    os.environ.setdefault("LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED", "1")
    from jiuwenswarm.server.live_voice.batch_speech import (
        ProviderSynthesisRequest,
        create_environment_batch_speech_provider,
    )

    provider = create_environment_batch_speech_provider()
    capability = provider.capability()
    if not (capability.available and capability.synthesis_batch):
        raise RuntimeError("configured batch synthesis Provider is unavailable")
    audio: dict[str, bytes] = {}
    for key, text in texts.items():
        result = await provider.synthesize(
            ProviderSynthesisRequest(f"lv-baseline-{key}-{uuid.uuid4().hex[:8]}", text, LOCALE, None, 24_000)
        )
        audio[key] = bytes(result.audio_wav)
    return audio


class Client:
    def __init__(self, socket: websockets.WebSocketClientProtocol) -> None:
        self.socket = socket
        self.seq = 0
        self._pending: dict[str, asyncio.Future] = {}
        self.events: list[dict] = []
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            while True:
                frame = json.loads(await self.socket.recv())
                if frame.get("type") == "res":
                    fut = self._pending.pop(str(frame.get("id")), None)
                    if fut is not None and not fut.done():
                        fut.set_result(frame)
                else:
                    self.events.append(frame)
        except Exception:  # noqa: BLE001
            return

    async def request(self, method: str, params: dict, timeout: float = 180.0) -> dict:
        self.seq += 1
        rid = f"lvb-{int(time.time())}-{self.seq}"
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self.socket.send(json.dumps({"type": "req", "id": rid, "method": method, "params": params}, ensure_ascii=False))
        return await asyncio.wait_for(fut, timeout=timeout)

    def close(self) -> None:
        self._reader.cancel()


def _ok(frame: dict) -> tuple[bool, dict]:
    payload = frame.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    if not frame.get("ok") and "error" not in payload:
        payload = {**payload, "error": frame.get("error"), "_frame_keys": sorted(frame)}
    return bool(frame.get("ok")), payload


def _media_url(endpoint_path: str | None) -> str:
    path = endpoint_path or "/ws/live-voice/media"
    return MEDIA_BASE + (path if path.startswith("/") else "/" + path)


async def one_round(client: Client, session_id: str, scenario: str, frames: list[tuple[float, ...]], last_speech: int, index: int, log: list[str]) -> dict:
    tag = f"{scenario}-{index}-{uuid.uuid4().hex[:6]}"
    r: dict = {"scenario": scenario, "round": index, "failures": [], "t": {}}
    t = r["t"]
    interaction_id, correlation_id, activation_id = f"lvb-int-{tag}", f"lvb-corr-{tag}", f"lvb-act-{tag}"
    capture_id, track_id = f"lvb-cap-{tag}", f"lvb-track-{tag}"
    route = {"session_id": session_id, "correlation_id": correlation_id, "interaction_id": interaction_id, "activation_id": activation_id, "activation_generation": 1}

    ok, payload = _ok(await client.request("live_voice.composition.p2.activate", route))
    if not ok:
        r["failures"].append(f"p2_activate:{json.dumps(payload, ensure_ascii=False)[:300]}")
        return r

    ok, media = _ok(await client.request("live_voice.media.activate", {**route, "capture_id": capture_id, "capture_generation": 1, "track_id": track_id, "sample_rate_hz": SAMPLE_RATE, "locale": LOCALE, "end_of_turn_capability": EOT_CAPABILITY}))
    ticket, binding = media.get("media_ticket"), media.get("binding")
    subject_id = media.get("subject_id")
    if not ok or not ticket or not isinstance(binding, dict):
        r["failures"].append(f"media_activate:{json.dumps(media, ensure_ascii=False)[:300]}")
        return r
    log.append(f"media.activate keys={sorted(media)} eot={media.get('end_of_turn')}")
    lease = str(binding.get("lease_id"))
    generation = int((binding.get("generation") or {}).get("value") or 0)

    eot_frame: dict | None = None
    attached = asyncio.Event()
    acks = 0
    async with websockets.connect(_media_url(media.get("endpoint_path")), open_timeout=20, max_size=8 << 20, subprotocols=[MEDIA_SUBPROTOCOL], **{_header_kwarg(): {"Origin": ORIGIN}}) as socket:
        await socket.send(json.dumps({"type": "media.auth", "contract_version": MEDIA_AUTH_CONTRACT, "media_ticket": ticket, "binding": binding}, ensure_ascii=False))

        async def drain() -> None:
            nonlocal acks, eot_frame
            try:
                while True:
                    raw = await socket.recv()
                    if isinstance(raw, (bytes, bytearray)):
                        continue
                    frame = json.loads(raw)
                    kind = str(frame.get("type"))
                    if kind == "media.attach":
                        attached.set()
                    elif kind == "media.ack":
                        acks += 1
                    elif kind == "media.end_of_turn":
                        t["eot_received"] = _now_ms()
                        eot_frame = frame
                    else:
                        log.append(f"media ctl: {kind} {json.dumps(frame, ensure_ascii=False)[:200]}")
            except Exception:  # noqa: BLE001
                return

        reader = asyncio.create_task(drain())
        try:
            await asyncio.wait_for(attached.wait(), timeout=15)
        except TimeoutError:
            r["failures"].append("media_attach")
            reader.cancel()
            return r
        t["first_frame_sent"] = _now_ms()
        cursor = 0
        sent = 0
        for seq, samples in enumerate(frames):
            await socket.send(_encode(lease, generation, seq, cursor, samples))
            sent += 1
            if seq == last_speech:
                t["speech_end"] = _now_ms()
            cursor += FRAME_SAMPLES
            if eot_frame is not None and seq > last_speech:
                break
            await asyncio.sleep(0.02)
        # Mirror the browser: keep the uplink open until the server has
        # acknowledged every sent frame (bounded), then settle and recognise.
        settle_deadline = time.perf_counter() + 10.0
        while time.perf_counter() < settle_deadline and (eot_frame is None or acks < sent):
            await asyncio.sleep(0.02)
        t["uplink_settled"] = _now_ms()
        reader.cancel()
    r["uplink_frames"], r["uplink_acks"] = sent, acks
    if eot_frame is None:
        r["failures"].append("end_of_turn")
        return r
    r["eot_detector"] = eot_frame.get("detector")

    recognize_params = {"session_id": session_id, "subject_id": subject_id, "correlation_id": correlation_id, "interaction_id": interaction_id, "capture_id": capture_id, "capture_generation": 1, "track_id": track_id}
    ok, rec = _ok(await client.request("live_voice.speech.recognize_streaming_result", recognize_params, timeout=90))
    if not ok and "absent or stale" in json.dumps(rec, ensure_ascii=False):
        # The Gateway registers the Provider final a beat after the uplink
        # settles; one bounded retry keeps a real round instead of dropping it
        # to this known ordering race (1/27 baseline rounds, 3/25 under load).
        await asyncio.sleep(0.3)
        r["recognition_retried"] = True
        ok, rec = _ok(await client.request("live_voice.speech.recognize_streaming_result", recognize_params, timeout=90))
    t["recognized"] = _now_ms()
    final_text = str(rec.get("final_text") or "")
    receipt = rec.get("voice_commit_receipt")
    r["recognition_status"] = rec.get("status")
    r["transcript_chars"] = len(final_text)
    if not ok or rec.get("status") != "completed" or not final_text or not receipt:
        r["failures"].append(f"recognition:{json.dumps(rec, ensure_ascii=False)[:300]}")
        return r

    commit_id, turn_id = f"lvb-commit-{tag}", f"lvb-turn-{tag}"
    t["submit_sent"] = _now_ms()
    ok, sub = _ok(await client.request("live_voice.composition.unified.submit", {**route, "commit_id": commit_id, "turn_id": turn_id, "committed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "text": final_text, "input_state": "final", "voice_commit_receipt": receipt}))
    t["submitted"] = _now_ms()
    if not ok:
        r["failures"].append(f"submit:{json.dumps(sub, ensure_ascii=False)[:300]}")
        return r
    log.append(f"submit keys={sorted(sub)}")

    final_note: dict | None = None
    first_note_at: float | None = None
    sequence, pulls = 1, 0
    deadline = time.perf_counter() + 240
    while time.perf_counter() < deadline and final_note is None:
        ok, note = _ok(await client.request("live_voice.composition.p2.notification.next", {**route, "notification_sequence": sequence, "max_notifications": NOTIFICATION_BATCH}, timeout=120))
        pulls += 1
        if not ok:
            expected = ((note.get("error") or {}).get("details") or {}).get("expected_sequence")
            if isinstance(expected, int) and expected != sequence:
                sequence = expected
                continue
            r["failures"].append(f"notification:{json.dumps(note, ensure_ascii=False)[:300]}")
            break
        inner = note.get("result")
        if pulls == 1:
            log.append(f"pull envelope keys={sorted(note)} result_keys={sorted(inner) if isinstance(inner, dict) else type(inner).__name__}")
        items: list[dict] = []
        if isinstance(inner, dict) and inner.get("status") == "notification":
            items = [inner]
        elif isinstance(inner, dict):
            for key in ("notifications", "items", "batch"):
                if isinstance(inner.get(key), list):
                    items = [x for x in inner[key] if isinstance(x, dict)]
                    break
        elif isinstance(inner, list):
            items = [x for x in inner if isinstance(x, dict)]
        if not items:
            await asyncio.sleep(0.05)
            continue
        for item in items:
            if first_note_at is None:
                first_note_at = _now_ms()
                log.append(f"first notification kind={item.get('kind')} keys={sorted(item)}")
            event = item.get("agent_event") or {}
            unit = item.get("presentation_unit") or {}
            seq_value = item.get("publish_seq", item.get("notification_sequence", item.get("sequence")))
            if isinstance(seq_value, int):
                sequence = max(sequence, seq_value + 1)
            else:
                sequence += 1
            if item.get("kind") == "agent.output" and event.get("event_type") == "chat.delta" and "first_delta" not in t:
                t["first_delta"] = _now_ms()
            if item.get("kind") == "agent.output" and event.get("event_type") == "chat.final" and unit:
                final_note = item
                break
    r["notification_pulls"] = pulls
    if first_note_at is not None:
        t["first_notification"] = first_note_at
    if final_note is None:
        r["failures"].append("agent_final")
        return r
    t["final_notification"] = _now_ms()
    answer = str((final_note.get("agent_event") or {}).get("text") or "")
    unit = final_note.get("presentation_unit") or {}
    response_ref = final_note.get("response") or {}
    r["answer_chars"] = len(answer)
    r["unit_surface"] = unit.get("surface")
    log.append(f"final unit keys={sorted(unit)} response keys={sorted(response_ref)}")

    ok, syn = _ok(await client.request("live_voice.speech.synthesize_batch", {"contract_version": SPEECH_CONTRACT, "request_id": f"lvb-syn-{tag}", "operation_id": f"lvb-synop-{tag}", "operation": "speech.synthesize.batch", "correlation_id": correlation_id, "session_id": session_id, "scope": {"subject_id": subject_id, "project_id": None, "session_id": session_id, "assurance": "authenticated"}, "timeout_ms": 30_000, "response": {"interaction_id": response_ref.get("interaction_id"), "response_id": response_ref.get("response_id"), "response_generation": response_ref.get("response_generation")}, "unit_id": unit.get("unit_id"), "render_plan": {"display_text": answer, "spoken_text": answer, "transforms": []}, "authoritative_agent_text": True, "locale": LOCALE, "voice": None, "required_sample_rate_hz": SAMPLE_RATE}, timeout=60))
    t["synthesis_returned"] = _now_ms()
    syn_result = syn.get("result") if isinstance(syn.get("result"), dict) else {}
    audio_desc = syn_result.get("audio") if isinstance(syn_result.get("audio"), dict) else {}
    down_ticket, down_binding = audio_desc.get("media_ticket"), audio_desc.get("binding")
    r["synthesis_streaming"] = audio_desc.get("streaming")
    if not ok or not down_ticket or not isinstance(down_binding, dict):
        r["failures"].append(f"synthesis:{json.dumps(syn, ensure_ascii=False)[:300]}")
        return r

    down_lease = str(down_binding.get("lease_id"))
    down_generation = int((down_binding.get("generation") or {}).get("value") or 0)
    received = 0
    async with websockets.connect(_media_url(audio_desc.get("endpoint_path")), open_timeout=20, max_size=8 << 20, subprotocols=[MEDIA_SUBPROTOCOL], **{_header_kwarg(): {"Origin": ORIGIN}}) as down:
        await down.send(json.dumps({"type": "media.auth", "contract_version": MEDIA_AUTH_CONTRACT, "media_ticket": down_ticket, "binding": down_binding}, ensure_ascii=False))
        deadline = time.perf_counter() + 90
        while time.perf_counter() < deadline:
            try:
                raw = await asyncio.wait_for(down.recv(), timeout=25)
            except BaseException:  # noqa: BLE001
                break
            if isinstance(raw, (bytes, bytearray)):
                if received == 0:
                    t["downlink_first_frame"] = _now_ms()
                seq = WIRE_HEADER.unpack_from(raw)[5]
                received += 1
                await down.send(json.dumps({"type": "media.ack", "contract_version": MEDIA_CONTRACT, "lease_id": down_lease, "generation": down_generation, "through_seq": seq}, ensure_ascii=False))
                if received >= 3:
                    break
                continue
            if str(json.loads(raw).get("type")) == "media.detach":
                break
    r["downlink_frames"] = received
    if received == 0:
        r["failures"].append("downlink")
    await client.request("live_voice.composition.p2.close", route, timeout=30)
    return r


def _segments(r: dict) -> dict[str, float | None]:
    t = r["t"]

    def d(a: str, b: str) -> float | None:
        return round(t[b] - t[a], 1) if a in t and b in t else None

    return {
        "speech_end->eot(VAD)": d("speech_end", "eot_received"),
        "eot->uplink_settled(ack drain)": d("eot_received", "uplink_settled"),
        "uplink_settled->recognized(STT final)": d("uplink_settled", "recognized"),
        "recognized->submit_sent": d("recognized", "submit_sent"),
        "submit_rpc_roundtrip(semantic resolve inside)": d("submit_sent", "submitted"),
        "submitted->first_notification": d("submitted", "first_notification"),
        "submitted->first_delta": d("submitted", "first_delta"),
        "submitted->final_notification": d("submitted", "final_notification"),
        "final->synthesis_returned(TTS first chunk)": d("final_notification", "synthesis_returned"),
        "synthesis->downlink_first_frame": d("synthesis_returned", "downlink_first_frame"),
        "TOTAL speech_end->downlink_first_frame": d("speech_end", "downlink_first_frame"),
    }


def _stats(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    n = len(values)

    def pct(fraction: float) -> float:
        if n == 1:
            return values[0]
        rank = fraction * (n - 1)
        low, high = int(rank), min(int(rank) + 1, n - 1)
        return values[low] + (values[high] - values[low]) * (rank - low)

    return {"n": n, "mean": round(statistics.fmean(values), 1), "p50": round(pct(0.5), 1), "p99": round(pct(0.99), 1), "max": round(values[-1], 1)}


async def main_async(args: argparse.Namespace) -> int:
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    scenarios = [s for s in args.scenarios.split(",") if s in SCENARIOS]
    print(f"synthesizing {len(scenarios)} fixtures ...", flush=True)
    fixture_texts: dict[str, str] = {}
    for k in scenarios:
        variants = SCENARIOS[k].get("texts")
        if variants:
            for i, text in enumerate(variants):
                fixture_texts[f"{k}#{i}"] = text
        else:
            fixture_texts[k] = SCENARIOS[k]["text"]
    audio = await synthesize_fixtures(fixture_texts)
    frames_by = {k: _wav_to_frames(v) for k, v in audio.items()}
    for k, (frames, last) in frames_by.items():
        print(f"  {k}: {len(frames)} frames, speech ends at frame {last} ({last * 20 / 1000:.2f}s)", flush=True)

    async with websockets.connect(WS_URL, open_timeout=20, max_size=8 << 20, **{_header_kwarg(): {"Origin": ORIGIN}}) as socket:
        client = Client(socket)
        ok, created = _ok(await client.request("session.create", {"create_token": str(uuid.uuid4()), "mode": "agent", "is_swarm": False, "title": "lv-latency-baseline", "work_mode": "code", "model_name": MODEL_NAME, "project_id": PROJECT_ID, "project_dir": PROJECT_DIR}))
        session_id = created.get("session_id") or (created.get("session") or {}).get("session_id")
        if not ok or not session_id:
            print(f"session.create failed: {json.dumps(created, ensure_ascii=False)[:500]}")
            return 2
        print(f"session {session_id}", flush=True)
        rounds_path = out / "rounds.jsonl"
        log: list[str] = []
        results: list[dict] = []
        with rounds_path.open("a", encoding="utf-8") as sink:
            for scenario in scenarios:
                variants = SCENARIOS[scenario].get("texts")
                for index in range(args.rounds):
                    key = f"{scenario}#{index % len(variants)}" if variants else scenario
                    frames, last = frames_by[key]
                    started = time.perf_counter()
                    try:
                        r = await one_round(client, session_id, scenario, frames, last, index, log)
                    except Exception as error:  # noqa: BLE001
                        r = {"scenario": scenario, "round": index, "failures": [f"exception:{type(error).__name__}:{str(error)[:200]}"], "t": {}}
                    r["wall_s"] = round(time.perf_counter() - started, 1)
                    r["segments"] = _segments(r)
                    results.append(r)
                    sink.write(json.dumps(r, ensure_ascii=False) + "\n")
                    sink.flush()
                    total = r["segments"].get("TOTAL speech_end->downlink_first_frame")
                    print(f"[{scenario} #{index}] total={total} ms answer={r.get('answer_chars')} fail={r['failures'][:1]} wall={r['wall_s']}s", flush=True)
                    await asyncio.sleep(args.gap_seconds)
        client.close()
    (out / "driver.log").write_text("\n".join(log), encoding="utf-8")

    summary: dict[str, dict] = {}
    for scenario in scenarios:
        rows = [r for r in results if r["scenario"] == scenario and not r["failures"]]
        segs: dict[str, dict] = {}
        for key in _segments({"t": {}}).keys():
            values = [r["segments"][key] for r in rows if r["segments"].get(key) is not None]
            if values:
                segs[key] = _stats(values)
        summary[scenario] = {"ok_rounds": len(rows), "failed_rounds": sum(1 for r in results if r["scenario"] == scenario and r["failures"]), "answer_chars_mean": round(statistics.fmean([r["answer_chars"] for r in rows]), 0) if rows else None, "segments": segs}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== SUMMARY (ms) ===")
    for scenario, item in summary.items():
        print(f"\n## {scenario}  ok={item['ok_rounds']} failed={item['failed_rounds']} answer_chars≈{item['answer_chars_mean']}")
        for key, st in item["segments"].items():
            print(f"  {key:44} n={st['n']} mean={st['mean']:>8} p50={st['p50']:>8} p99={st['p99']:>8} max={st['max']:>8}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--scenarios", default="short,medium,long,tool,task")
    parser.add_argument("--gap-seconds", type=float, default=1.0)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "logs" / f"lv-latency-baseline-{time.strftime('%Y%m%d-%H%M%S')}"))
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

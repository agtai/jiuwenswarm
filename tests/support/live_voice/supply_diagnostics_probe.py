"""Production downlink loop, yielding socket I/O and actual bounded log sink.

Run as a module with --output beneath a dedicated local evidence directory.
--baseline-redaction reads only the named revision's logging implementation;
it does not checkout, rewrite source, access user data, or contact a Provider.
This is mechanism evidence, not browser/acoustic acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import statistics
import subprocess
import time
from dataclasses import replace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline-redaction")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Must precede imports that initialize common.utils and production logging.
    os.environ["JIUWENSWARM_DATA_DIR"] = str(args.output.parent / "probe-data")
    from jiuwenswarm.common import utils, live_voice_audio_diagnostics as diagnostics
    from jiuwenswarm.gateway.live_voice import dedicated_media_route as route
    from tests.unit_tests.gateway import test_dedicated_live_voice_media_route as fixtures

    if args.baseline_redaction:
        source = subprocess.check_output(["git", "show",
            f"{args.baseline_redaction}:jiuwenswarm/common/utils.py"], encoding="utf-8")
        namespace = dict(vars(utils))
        exec(compile(source[source.index('_SENSITIVE_MASK ='):source.index('def setup_logger(')],
            "baseline-redaction", "exec"), namespace)
        logging.setLogRecordFactory(logging.LogRecord)
        namespace["install_source_record_masking"]()
        for handler in logging.getLogger("jiuwenswarm").handlers:
            for filter_ in tuple(handler.filters):
                if isinstance(filter_, utils.SensitiveDataFilter):
                    handler.removeFilter(filter_)
                    handler.addFilter(namespace["SensitiveDataFilter"]())

    async def run(on, background):
        await asyncio.to_thread(diagnostics._QUEUE.join)
        original = route.record_audio_diagnostic
        if not on:
            route.record_audio_diagnostic = lambda *a, **kw: None
        binding = fixtures._downlink_binding()
        suffix = "-" + "ab9c04d7" * 8
        binding = replace(binding, session_id="web" + suffix,
            media_session_id="native-media" + suffix, interaction_id="interaction" + suffix,
            lease_id="lease" + suffix)
        sent_at, samples, lags, scheduler_delays, pcm_bytes, wire_bytes = [], [], [], [], [], []
        done = asyncio.Event()
        queue_peak = 0
        dropped_before = diagnostics._DROPPED

        class Socket(fixtures._ControlledDownlinkSocket):
            async def send(self, message):
                # Actual thread sleep releases the GIL. A synchronous fake or
                # asyncio.sleep(0) hides the diagnosed production mechanism.
                await asyncio.to_thread(time.sleep, .001)
                self.sent.append(message)
                if isinstance(message, bytes):
                    sent_at.append(time.perf_counter())
                    frame = fixtures.decode_audio_frame(binding, message)
                    assert message == fixtures.encode_audio_frame(
                        binding, fixtures._frame(frame.seq, frame.seq * 160))
                    wire_bytes.append(message)
                    pcm_bytes.append(message[-len(frame.samples) * 4:])
                    samples.append((frame.seq, frame.sample_cursor, frame.samples))
                    self.controls.put_nowait(fixtures.serialize_media_control(
                        fixtures.MediaAck(binding.lease_id, binding.generation.value, frame.seq)))

        async def observe():
            nonlocal queue_peak
            while not done.is_set():
                before = time.perf_counter()
                await asyncio.to_thread(time.sleep, .002)
                scheduler_delays.append(max(0, (time.perf_counter() - before) * 1000 - 2))
                queue_peak = max(queue_peak, diagnostics._QUEUE.qsize())

        async def loop_clock():
            while not done.is_set():
                # perf_counter avoids the coarse Windows loop.time clock
                # rounding a measured timer overrun down to exactly zero.
                deadline = time.perf_counter() + .010
                while (remaining := deadline - time.perf_counter()) > 0:
                    await asyncio.sleep(remaining)
                lags.append(max(0, (time.perf_counter() - deadline) * 1000))

        async def load():
            while not done.is_set():
                if background:
                    await asyncio.to_thread(hashlib.pbkdf2_hmac, "sha256", b"test-load", b"test-salt", 3000)
                await asyncio.sleep(.01)

        observer, work, timer = (asyncio.create_task(observe()),
            asyncio.create_task(load()), asyncio.create_task(loop_clock()))
        start, cpu = time.perf_counter(), time.process_time()
        try:
            result = await route.run_dedicated_media_downlink_socket_leaf(
                fixtures._request(binding), socket=Socket(), frames=fixtures._ReadyDownlinkFrames(50),
                on_playback_stop=lambda _: None, max_pending_frames=8)
            elapsed = (time.perf_counter() - start) * 1000
            assert result.sent_frames == 50 and result.acknowledged_through_seq == 49
            assert [entry[0] for entry in samples] == list(range(50))
            assert [entry[1] for entry in samples] == [160 * i for i in range(50)]
        finally:
            done.set()
            await asyncio.gather(observer, work, timer)
            route.record_audio_diagnostic = original
            await asyncio.to_thread(diagnostics._QUEUE.join)
        cpu_ms = (time.process_time() - cpu) * 1000
        return dict(diagnostics=on, background=background, frames=50,
            first_8_span_ms=(sent_at[7] - sent_at[0]) * 1000,
            all_50_span_ms=(sent_at[-1] - sent_at[0]) * 1000,
            process_cpu_ms=cpu_ms, elapsed_ms=elapsed,
            loop_lag_p95_ms=sorted(lags)[min(len(lags)-1, int(len(lags)*.95))],
            loop_lag_max_ms=max(lags), queue_peak=queue_peak,
            loop_lag_samples=len(lags),
            scheduler_round_trip_p95_ms=sorted(scheduler_delays)[min(len(scheduler_delays)-1, int(len(scheduler_delays)*.95))],
            dropped=diagnostics._DROPPED-dropped_before,
            pcm_sha256=hashlib.sha256(b"".join(pcm_bytes)).hexdigest(),
            wire_sha256=hashlib.sha256(b"".join(wire_bytes)).hexdigest(),
            sequence_errors=0, duplicate_frames=0, missing_frames=0)

    async def all_runs():
        return [await run(on, background) for background in (False, True)
                for _ in range(4) for on in (False, True)]
    runs = asyncio.run(all_runs())
    report = {"redaction": args.baseline_redaction or "working-source",
        "loop_clock": vars(time.get_clock_info("monotonic")),
        "measurement_clock": vars(time.get_clock_info("perf_counter")),
        "handler_count": len(logging.getLogger("jiuwenswarm").handlers),
        "queue_capacity": diagnostics._QUEUE.maxsize, "runs": runs, "groups": []}
    for background in (False, True):
        for on in (False, True):
            group = [run for run in runs if run["diagnostics"] == on and run["background"] == background]
            report["groups"].append({"background": background, "diagnostics": on, "n": len(group),
                **{key: statistics.median(run[key] for run in group) for key in (
                    "first_8_span_ms", "all_50_span_ms", "process_cpu_ms", "loop_lag_p95_ms", "queue_peak")}})
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["groups"], indent=2))


if __name__ == "__main__":
    main()

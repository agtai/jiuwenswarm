"""Owned headless Chrome audio harness; no user's browser/profile/credentials.

This small controller reuses the existing secure L0 socket/process checks and
CDP client. Business speech enters a MediaStream; never a transcript/Task RPC.
Commands are test-side JSON files to keep every attempt and resulting evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import subprocess
import time
import wave
from pathlib import Path
from urllib.parse import urlsplit

from scripts.live_voice.l0_browser_capture import (
    _CdpClient,
    _read_browser_pages,
    _loopback_websocket,
    _connect_owned_browser_socket,
    _browser_websocket_connect,
    _assert_browser_socket_owner,
)


def validate_target_url(value: str) -> str:
    """This test controller must never navigate to an external/user account."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("audio harness requires an explicit loopback HTTP target")
    if parsed.port is None or not 1 <= parsed.port <= 65535:
        raise ValueError("audio harness requires an explicit loopback port")
    return value


def read_sample_audio(audio_dir: Path, sample) -> bytes:
    root = audio_dir.resolve()
    relative = Path(sample["file"])
    path = (root / relative).resolve()
    if (
        relative.is_absolute()
        or not path.is_relative_to(root)
        or path.suffix.lower() != ".wav"
    ):
        raise ValueError("audio sample must stay inside its owned WAV cache")
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("audio sample missing or over test input bound")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sample["sha256"]:
        raise ValueError("audio digest mismatch")
    return raw


async def run(options):
    validate_target_url(options.url)
    root = options.output_dir.resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("browser output must be new/empty")
    root.mkdir(parents=True, exist_ok=True)
    profile = root / "chrome-profile"
    # This is a disposable headless browser, not a selected existing user tab.
    process = subprocess.Popen(
        [
            str(options.chrome),
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={options.port}",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = {
        "browser_endpoint": f"http://127.0.0.1:{options.port}",
        "browser_debugger_process_id": process.pid,
        "browser_launch_process_id": process.pid,
        "browser_executable_path": str(options.chrome.resolve()),
        "browser_profile_path": str(profile),
    }
    manifest = json.loads(
        (options.audio_dir / "manifest.json").read_text(encoding="utf-8-sig")
    )
    samples = {row["id"]: row for row in manifest["samples"]}
    evidence = root / "events.jsonl"
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                pages = await asyncio.to_thread(_read_browser_pages, session)
                break
            except RuntimeError:
                if time.monotonic() >= deadline or process.poll() is not None:
                    raise
                await asyncio.sleep(0.2)
        targets = [
            row
            for row in pages
            if row.get("type") == "page" and row.get("url") == "about:blank"
        ]
        if len(targets) != 1:
            raise RuntimeError("expected exact owned initial page")
        url = _loopback_websocket(
            targets[0]["webSocketDebuggerUrl"], expected_port=options.port
        )
        owned_socket = await asyncio.to_thread(_connect_owned_browser_socket, session)
        owned_socket.setblocking(False)
        async with _browser_websocket_connect(url, owned_socket) as connection:
            _assert_browser_socket_owner(session, owned_socket)
            client = _CdpClient(connection)
            await client.command("Page.enable")
            script = (
                Path(__file__).resolve().parents[2]
                / "tests/support/live_voice/audio_journey/browser_audio.js"
            ).read_text(encoding="utf-8")
            await client.command(
                "Page.addScriptToEvaluateOnNewDocument", {"source": script}
            )
            await client.command("Page.navigate", {"url": options.url})
            (root / "ready.json").write_text(
                json.dumps(
                    {
                        "pid": process.pid,
                        "url": options.url,
                        "injection": "getUserMedia audio MediaStream",
                        "physical_audio": False,
                    }
                ),
                encoding="utf-8",
            )
            processed = set()
            observation_sequence = 0
            while not (root / "stop.request").exists():
                for command_path in sorted(root.glob("command-*.json")):
                    if (
                        command_path.name.endswith(".result.json")
                        or command_path.name in processed
                    ):
                        continue
                    command = json.loads(command_path.read_text(encoding="utf-8-sig"))
                    result = {"command": command, "status": "FAIL"}
                    try:
                        kind = command["kind"]
                        if kind == "speak":
                            sample = samples[command["sample"]]
                            raw = read_sample_audio(options.audio_dir, sample)
                            result["result"] = await client.evaluate(
                                f"window.__semanticAudioTest.play({json.dumps(base64.b64encode(raw).decode())},{json.dumps(sample['id'])})"
                            )
                        elif kind == "ui":
                            # Test selectors/action only; do not expose arbitrary JS or product internals.
                            selector = json.dumps(command["selector"])
                            exact_text = command.get("text")
                            lookup = (
                                f"document.querySelector({selector})"
                                if exact_text is None
                                else f"[...document.querySelectorAll({selector})].find(e=>e.innerText.trim()==={json.dumps(exact_text)})"
                            )
                            if command["action"] == "click":
                                expression = f"(()=>{{const e={lookup};if(!e||e.disabled)throw Error('element missing or disabled');e.click();return true}})()"
                            elif command["action"] == "fill":
                                value = json.dumps(command["value"])
                                expression = f"(()=>{{const e=document.querySelector({selector});if(!e)throw Error('element missing');const p=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,{value});e.dispatchEvent(new Event('input',{{bubbles:true}}));return true}})()"
                            elif command["action"] == "type":
                                await client.evaluate(
                                    f"(()=>{{const e={lookup};if(!e)throw Error('element missing');e.focus();return true}})()"
                                )
                                result["result"] = await client.command(
                                    "Input.insertText", {"text": command["value"]}
                                )
                                expression = "true"
                            elif command["action"] == "enter":
                                await client.command(
                                    "Input.dispatchKeyEvent",
                                    {
                                        "type": "keyDown",
                                        "key": "Enter",
                                        "code": "Enter",
                                        "windowsVirtualKeyCode": 13,
                                    },
                                )
                                await client.command(
                                    "Input.dispatchKeyEvent",
                                    {
                                        "type": "keyUp",
                                        "key": "Enter",
                                        "code": "Enter",
                                        "windowsVirtualKeyCode": 13,
                                    },
                                )
                                expression = "true"
                            else:
                                raise ValueError("unsupported UI action")
                            result["result"] = await client.evaluate(expression)
                        elif kind == "refresh":
                            result["result"] = await client.command("Page.reload")
                        elif kind == "snapshot":
                            result["result"] = await client.evaluate(
                                "({url:location.href,text:document.body.innerText,audio:window.__semanticAudioTest?.snapshot(),audio_api:typeof AudioContext,media_api:typeof navigator.mediaDevices,controls:[...document.querySelectorAll('button,input,select,textarea')].map(e=>({tag:e.tagName,type:e.type,text:e.innerText,title:e.title,aria:e.getAttribute('aria-label'),placeholder:e.placeholder,disabled:e.disabled}))})"
                            )
                            shot = await client.command(
                                "Page.captureScreenshot", {"format": "png"}
                            )
                            (root / (command_path.stem + ".png")).write_bytes(
                                base64.b64decode(shot["data"])
                            )
                        else:
                            raise ValueError("unsupported command")
                        result["status"] = (
                            "PASS"  # Tool action only, NOT scenario pass.
                        )
                    except Exception as error:
                        result["error"] = type(error).__name__
                    target = root / (command_path.stem + ".result.json")
                    temporary = target.with_suffix(".json.tmp")
                    temporary.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    temporary.replace(target)
                    processed.add(command_path.name)
                batch = await client.evaluate(
                    "window.__semanticAudioTest?.drain() ?? []"
                )
                with evidence.open("a", encoding="utf-8") as output:
                    for event in batch:
                        observation_sequence += 1
                        event["document_sequence"] = event["sequence"]
                        event["sequence"] = observation_sequence
                        encoded = event.pop("pcm_s16le_base64", None)
                        if encoded is not None:
                            pcm = base64.b64decode(encoded)
                            filename = f"{event['id']}.wav"
                            with wave.open(str(root / filename), "wb") as audio:
                                audio.setnchannels(1)
                                audio.setsampwidth(2)
                                audio.setframerate(event["sample_rate"])
                                audio.writeframes(pcm)
                            event.update(
                                file=filename,
                                pcm_sha256=hashlib.sha256(pcm).hexdigest(),
                            )
                        output.write(json.dumps(event, ensure_ascii=False) + "\n")
                await asyncio.sleep(0.05)
            try:
                await client.command("Browser.close")
            except Exception:
                if process.poll() is None:
                    raise
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=8)
        (root / "cleanup.json").write_text(
            json.dumps({"owned_browser_stopped": True}), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--chrome",
        type=Path,
        default=Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    )
    parser.add_argument("--port", type=int, default=9299)
    asyncio.run(run(parser.parse_args()))

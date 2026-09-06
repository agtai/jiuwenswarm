"""Physical-LOC inventory of the official Hermes (NousResearch/hermes-agent) voice surface.

Usage: python hermes_voice_inventory.py --repo PATH [--json OUT]

The script never modifies the Hermes checkout. It reports three things with one explicit counting
rule (physical lines: blank, comment and docstring lines count):

1. the curated dedicated voice production files by category (whole files);
2. voice-named symbol segments inside shared hosts (gateway, platform adapters, CLI/TUI mixins),
   where a symbol counts when its name mentions voice/tts/transcription/transcribe/stt/audio/
   speech/barge/wake word; plain ``transcript`` names are chat-log code and are excluded;
3. voice-related test files by filename.

Known limits: the segment scan covers Python hosts only (the TUI/desktop TypeScript hosts also carry
a few hundred voice lines that are not counted); ``plugins/<non-platform>/*.py`` and non-dedicated
``tools/*.py`` are outside HOST_GLOBS; the wake-word category lists the three core files only (the
desktop wake indicator/capture files add roughly 0.8K more, all outside the comparable set).

The curated list is the review baseline for the comparison document; if the Hermes tree moves,
rerun with the new checkout and update the document's provenance line.
"""
from __future__ import annotations

import argparse
import ast
import glob
import io
import json
import os
import re
import subprocess
import tokenize
import warnings

CATEGORIES = {
    "A CLI/TUI voice loop": [
        "tools/voice_mode.py", "tools/voice_mode_transcript.py", "hermes_cli/cli_voice_mixin.py",
        "hermes_cli/voice.py", "tui_gateway/methods_voice.py",
    ],
    "B STT providers": [
        "tools/transcription_tools.py", "tools/transcription_cloud.py", "tools/transcription_audio.py",
        "tools/transcription_local.py", "tools/transcription_command.py", "tools/transcription_common.py",
        "tools/audio_container.py", "agent/transcription_provider.py", "agent/transcription_registry.py",
    ],
    "C TTS providers": [
        "tools/tts_tool.py", "tools/tts_tool_providers.py", "tools/tts_tool_delivery.py",
        "tools/tts_tool_speaker.py", "tools/tts_tool_lifecycle.py", "tools/tts_tool_local.py",
        "tools/tts_tool_openai.py", "tools/tts_tool_plugins.py", "tools/tts_command_provider.py",
        "tools/tts_text_normalize.py", "tools/tts_streaming.py", "tools/neutts_synth.py",
        "agent/tts_provider.py", "agent/tts_registry.py",
    ],
    "D Gateway/web voice": [
        "gateway/run_voice.py", "gateway/streaming_tts_consumer.py", "hermes_cli/web_routers/audio.py",
        "tools/voice_client_config.py",
    ],
    "E Desktop voice": [
        "apps/desktop/src/lib/voice-playback.ts",
        "apps/desktop/src/app/chat/composer/hooks/use-voice-conversation.ts",
        "apps/desktop/src/lib/voice-client-direct.ts",
        "apps/desktop/src/app/chat/composer/hooks/use-composer-voice.ts",
        "apps/desktop/src/lib/voice-barge-in.ts",
        "apps/desktop/src/app/chat/composer/hooks/use-mic-recorder.ts",
        "apps/desktop/src/app/chat/composer/voice-activity.tsx", "apps/desktop/src/lib/speech-text.ts",
        "apps/desktop/src/app/chat/composer/voice-menu.tsx",
        "apps/desktop/src/app/settings/voice-provider-fields.tsx",
        "apps/desktop/src/app/chat/composer/hooks/use-voice-recorder.ts",
        "apps/desktop/src/lib/voice-stop-word.ts", "apps/desktop/src/lib/tts-lease.ts",
        "apps/desktop/src/store/voice-prefs.ts", "apps/desktop/src/lib/audio-context.ts",
        "apps/desktop/src/store/voice-playback.ts",
        "apps/desktop/src/app/chat/composer/hooks/use-auto-speak-replies.ts",
        "apps/desktop/src/lib/thinking-sound.ts",
    ],
    "F Platform voice (dedicated)": [
        "plugins/platforms/discord/voice_mixer.py", "plugins/google_meet/audio_bridge.py",
    ],
    "G Wake word (Hermes-only)": [
        "tools/wake_word.py", "tools/wake_word_engines.py", "apps/desktop/src/store/wake-word.ts",
    ],
    "H Realtime speak-only client (Native analogue, excluded)": [
        "plugins/google_meet/realtime/openai_client.py", "plugins/google_meet/realtime/__init__.py",
    ],
    "I Setup/support (excluded from the comparable set)": [
        "hermes_cli/setup_tts.py", "scripts/discord-voice-doctor.py",
    ],
}
EXCLUDED_FROM_COMPARABLE = {
    "G Wake word (Hermes-only)", "H Realtime speak-only client (Native analogue, excluded)",
    "I Setup/support (excluded from the comparable set)",
}
DEDICATED_RX = re.compile(
    r"voice_mixer|run_voice|streaming_tts_consumer|methods_voice|cli_voice_mixin|hermes_cli/voice\.py|"
    r"setup_tts|tts_|transcription_|voice_mode|voice_client_config|wake_word|web_routers/audio", re.I)
SEGMENT_RX = re.compile(r"voice|tts|transcription|transcribe|(^|_)stt(_|$)|audio|speech|barge|wake_word|hotword", re.I)
HOST_GLOBS = ("gateway/platforms/*.py", "plugins/platforms/*/*.py", "gateway/*.py", "tui_gateway/*.py",
              "hermes_cli/*.py", "agent/*.py", "cli.py", "run_agent.py")
TEST_NAME_RX = re.compile(r"voice|tts|transcri|stt_|_stt|speech|audio|wake[_-]?word|barge|hotword|whisper|neutts|piper|kitten", re.I)
TEST_EXCL_RX = re.compile(r"atomic|yaml|transcript-(tail|window|backfill|directive|provenance|band)|read-only-transcript|"
                          r"session_transcript|transcript_repair|youtube|fetch_transcript|check_parity", re.I)


def read(repo: str, rel: str) -> str:
    return io.open(os.path.join(repo, rel), encoding="utf-8", errors="replace").read()


def non_behaviour(path: str, text: str) -> tuple[int, int]:
    lines = text.splitlines()
    blank = sum(1 for l in lines if not l.strip())
    if path.endswith(".py"):
        comment = doc = 0
        try:
            comment = sum(1 for tok in tokenize.generate_tokens(io.StringIO(text).readline) if tok.type == tokenize.COMMENT)
        except Exception:
            pass
        try:
            for node in ast.walk(ast.parse(text)):
                if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body
                        and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    doc += node.body[0].end_lineno - node.body[0].lineno + 1
        except Exception:
            pass
        return len(lines), blank + comment + doc
    return len(lines), blank + sum(1 for l in lines if l.strip().startswith(("//", "/*", "*")))


def segments(repo: str, rel: str) -> tuple[int, list[str]]:
    """Voice-named top-level symbols and methods; a counted class does not double count its methods."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(read(repo, rel))
    total = 0
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if SEGMENT_RX.search(node.name):
                total += node.end_lineno - node.lineno + 1
                names.append(node.name)
                continue
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and SEGMENT_RX.search(member.name):
                    total += member.end_lineno - member.lineno + 1
                    names.append(member.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and SEGMENT_RX.search(node.name):
            total += node.end_lineno - node.lineno + 1
            names.append(node.name)
    return total, names


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()
    repo = args.repo
    head = subprocess.run(["git", "log", "-1", "--format=%H %ci"], cwd=repo, capture_output=True, encoding="utf-8").stdout.strip()
    print(f"Hermes checkout: {repo} @ {head}")

    report: dict = {"head": head, "categories": {}, "segments": [], "tests": {}}
    print("\n== dedicated voice production files (whole files) ==")
    grand = grand_nb = comparable = 0
    for cat, files in CATEGORIES.items():
        loc = nb = 0
        for rel in files:
            text = read(repo, rel)
            n, b = non_behaviour(rel, text)
            loc += n
            nb += b
        report["categories"][cat] = {"files": len(files), "loc": loc, "non_behaviour": nb}
        print(f"{cat:<58}{len(files):>3} files {loc:>8,} LOC  non-behaviour {100 * nb / loc:3.0f}%")
        grand += loc
        grand_nb += nb
        if cat not in EXCLUDED_FROM_COMPARABLE:
            comparable += loc
    print(f"{'dedicated total':<58}{sum(len(v) for v in CATEGORIES.values()):>3} files {grand:>8,} LOC  non-behaviour {100 * grand_nb / grand:3.0f}%")
    print(f"{'dedicated comparable (A-F)':<58}{'':>9} {comparable:>8,} LOC")

    print("\n== voice-named symbol segments inside shared hosts ==")
    seg_total = 0
    paths: set[str] = set()
    for pattern in HOST_GLOBS:
        paths.update(p.replace("\\", "/") for p in glob.glob(os.path.join(repo, pattern)))
    rows = []
    for path in sorted(paths):
        rel = os.path.relpath(path, repo).replace("\\", "/")
        if DEDICATED_RX.search(rel):
            continue
        try:
            n, names = segments(repo, rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        if n:
            rows.append((n, rel, names))
            seg_total += n
    for n, rel, names in sorted(rows, reverse=True):
        print(f"{n:5d} {rel}  {', '.join(names[:5])}{' ...' if len(names) > 5 else ''}")
        report["segments"].append({"loc": n, "path": rel, "symbols": names})
    print(f"shared-host voice segments: {seg_total:,} LOC in {len(rows)} files")
    print(f"\nHermes voice production total: {grand + seg_total:,} (dedicated {grand:,} + segments {seg_total:,})")
    print(f"Hermes voice comparable set:   {comparable + seg_total:,} (A-F {comparable:,} + segments {seg_total:,})")

    tracked = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, encoding="utf-8").stdout.splitlines()
    tf = tl = 0
    for rel in tracked:
        if (TEST_NAME_RX.search(rel) and not TEST_EXCL_RX.search(rel) and rel.endswith((".py", ".ts", ".tsx"))
                and re.search(r"(^|/)(tests?|__tests__)(/|$)|\.test\.", rel)):
            tf += 1
            tl += len(read(repo, rel).splitlines())
    report["tests"] = {"files": tf, "loc": tl}
    print(f"\nvoice-related test files: {tf} files, {tl:,} LOC")
    if args.json:
        io.open(args.json, "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

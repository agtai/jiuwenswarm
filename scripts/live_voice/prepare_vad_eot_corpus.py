"""Create the private fixed-pause corpus for VAD/EOT screening."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from vad_eot_benchmark_support import PrepareVadCorpusRequest, prepare_vad_corpus


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CORPUS_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class _ClosedParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise ValueError("VAD_CORPUS_ARGUMENT_INVALID")


def _absolute(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or any(character in value for character in "\r\n\0"):
        raise ValueError("VAD_CORPUS_ARGUMENT_INVALID")
    return path


def parse_args(argv: list[str]) -> PrepareVadCorpusRequest:
    parser = _ClosedParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--source-wav", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--split-frame", required=True)
    parser.add_argument("--private-expectation-json", required=True)
    parsed = parser.parse_args(argv)
    if not _SHA256.fullmatch(parsed.source_sha256) or not _CORPUS_ID.fullmatch(parsed.corpus_id):
        raise ValueError("VAD_CORPUS_ARGUMENT_INVALID")
    if not re.fullmatch(r"[1-9][0-9]{0,9}", parsed.split_frame):
        raise ValueError("VAD_CORPUS_ARGUMENT_INVALID")
    return PrepareVadCorpusRequest(
        source_wav=_absolute(parsed.source_wav),
        source_sha256=parsed.source_sha256,
        output_root=_absolute(parsed.output_root),
        corpus_id=parsed.corpus_id,
        split_frame=int(parsed.split_frame),
        expectation_json=_absolute(parsed.private_expectation_json),
    )


def main(argv: list[str] | None = None) -> int:
    request = parse_args(list(sys.argv[1:] if argv is None else argv))
    manifest = prepare_vad_corpus(request)
    sys.stdout.write(json.dumps({"corpus_id": manifest.corpus_id}, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        sys.stderr.write("VAD_EOT_CORPUS_FAILED\n")
        raise SystemExit(1) from None

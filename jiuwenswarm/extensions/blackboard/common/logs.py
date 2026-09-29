"""Blackboard's own log file, next to its data."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "jiuwenswarm.extensions.blackboard"
_HANDLER_MARK = "_blackboard_file_handler"

# Member and bot tokens, signed document and file tokens (three base64url parts), the `t=` of a
# download link, and a bearer header.
_SECRETS = re.compile(
    r"(?P<prefix>bb[mb]_)[A-Za-z0-9_-]{8,}"
    r"|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"|(?P<query>[?&]t=)[^&\s\"']+"
    r"|(?P<bearer>Bearer )[A-Za-z0-9._~+/=-]+"
)


def redact(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return (match.group("prefix") or match.group("query") or match.group("bearer") or "") + "[redacted]"

    return _SECRETS.sub(replace, text)


class RedactingFormatter(logging.Formatter):
    """Tokens never reach blackboard.log, whatever a message or a traceback holds."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_file_logging(directory: Path, file_name: str = "blackboard.log") -> None:
    """Attach a rotating file handler once per process (20 MB, 5 files)."""
    logger = logging.getLogger(LOGGER_NAME)
    if any(getattr(h, _HANDLER_MARK, False) for h in logger.handlers):
        return
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / file_name, maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    setattr(handler, _HANDLER_MARK, True)
    logger.addHandler(handler)
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

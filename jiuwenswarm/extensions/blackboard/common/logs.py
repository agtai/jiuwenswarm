"""Blackboard's own log file, next to its data."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "jiuwenswarm.extensions.blackboard"
_HANDLER_MARK = "_blackboard_file_handler"


def setup_file_logging(directory: Path, file_name: str = "blackboard.log") -> None:
    """Attach a rotating file handler once per process (20 MB, 5 files)."""
    logger = logging.getLogger(LOGGER_NAME)
    if any(getattr(h, _HANDLER_MARK, False) for h in logger.handlers):
        return
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / file_name, maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    setattr(handler, _HANDLER_MARK, True)
    logger.addHandler(handler)
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

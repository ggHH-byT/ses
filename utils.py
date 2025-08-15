from __future__ import annotations
import os
from pathlib import Path
from loguru import logger

def ensure_dirs(*paths: str | os.PathLike):
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)

def path_join(*parts) -> str:
    return str(Path(*parts).resolve())

def setup_logging(logs_dir: str):
    ensure_dirs(logs_dir)
    logger.remove()
    logger.add(Path(logs_dir) / "app.log", rotation="10 MB", retention="14 days", enqueue=True, level="INFO")
    logger.add(lambda msg: print(msg, end=""), level="INFO")

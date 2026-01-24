from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional


_LOGGER = logging.getLogger("icpa")


def _extract_trace_id() -> Optional[str]:
    trace_header = os.getenv("_X_AMZN_TRACE_ID")
    if not trace_header:
        return None
    parts = trace_header.split(";")
    for part in parts:
        if part.startswith("Root="):
            return part.replace("Root=", "")
    return None


def get_logger() -> logging.Logger:
    if not _LOGGER.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        _LOGGER.addHandler(handler)
        _LOGGER.setLevel(logging.INFO)
    return _LOGGER


def log_json(message: str, **fields: Any) -> None:
    logger = get_logger()
    payload: Dict[str, Any] = {"message": message}
    trace_id = _extract_trace_id()
    if trace_id:
        payload["trace_id"] = trace_id
    payload.update(fields)
    logger.info(json.dumps(payload, default=str))

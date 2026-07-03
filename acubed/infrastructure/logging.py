# infrastructure/logging.py

import logging
from typing import Any

_CONFIGURED = False


def get_logger() -> logging.Logger:
    global _CONFIGURED

    if not _CONFIGURED:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        )

        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        _CONFIGURED = True

    return logging.getLogger("acubed")


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"

    text = str(value)
    if any(char.isspace() for char in text):
        return repr(text)
    return text


def log_event(
    logger: logging.Logger,
    event: str,
    /,
    **fields: Any,
) -> None:
    parts = [f"event={event}"]
    parts.extend(
        f"{key}={_format_value(value)}"
        for key, value in fields.items()
        if value is not None
    )
    logger.info(" ".join(parts))


def log_warning_event(
    logger: logging.Logger,
    event: str,
    /,
    **fields: Any,
) -> None:
    parts = [f"event={event}"]
    parts.extend(
        f"{key}={_format_value(value)}"
        for key, value in fields.items()
        if value is not None
    )
    logger.warning(" ".join(parts))

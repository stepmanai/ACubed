# infrastructure/logging.py

import logging

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

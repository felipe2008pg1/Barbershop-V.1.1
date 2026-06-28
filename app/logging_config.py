"""
Central logging configuration.

Sets up a consistent log format across the whole app, writing to both
the console (for `uvicorn --reload` development) and a rotating log
file (so production deployments keep a history without growing
unbounded on disk).
"""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "barbershop.log")

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Third-party loggers that are noisy at INFO level and not useful for
# day-to-day debugging of this app. Always silenced, even in debug mode,
# since they mostly just log internal housekeeping (e.g. every file
# change detected by --reload, or every HTTP connection opened).
_ALWAYS_QUIET_LOGGERS = [
    "watchfiles",
    "watchfiles.main",
    "uvicorn.access",
]


def configure_logging(debug: bool = False) -> None:
    """
    Configures the root logger once at application startup.

    - Console handler: always active, useful for `uvicorn --reload`.
    - Rotating file handler: keeps up to 5 files of 2MB each, so logs
      don't grow forever but recent history is preserved for debugging
      production issues.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers if this is called more than once
    # (e.g. due to --reload triggering a re-import).
    if not root_logger.handlers:
        formatter = logging.Formatter(LOG_FORMAT)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Always quiet down file-watcher and access-log noise.
    for noisy_logger in _ALWAYS_QUIET_LOGGERS:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # Quiet down other noisy third-party loggers unless we're in debug mode.
    if not debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("hpack").setLevel(logging.WARNING)

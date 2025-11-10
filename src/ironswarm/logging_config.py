import logging
import sys
from logging.handlers import RotatingFileHandler


def configure_logging(level=logging.INFO, log_file=None):
    """
    Configure logging for the entire project.

    Args:
        level (int or str): Logging level, e.g. logging.DEBUG or "DEBUG".
        log_file (str or None): Path to a log file to write logs into.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Clear any existing handlers (avoids duplicate logs if re-run)
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():  # pragma: no branch
        root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-2s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    handlers = [console_handler]

    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)

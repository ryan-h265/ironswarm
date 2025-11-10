import logging

from ironswarm.logging_config import configure_logging


def test_configure_logging_default_level():
    configure_logging()
    logger = logging.getLogger()
    assert logger.level == logging.INFO
    assert len(logger.handlers) > 0


def test_configure_logging_invalid_level():
    configure_logging(level="INVALID")
    logger = logging.getLogger()
    assert logger.level == logging.INFO  # Default level should be INFO


def test_configure_logging_multiple_handlers(tmp_path):
    log_file = tmp_path / "test.log"
    configure_logging(level="WARNING", log_file=str(log_file))

    logger = logging.getLogger()
    assert len(logger.handlers) == 2  # Console and file handlers

    logger.warning("Test warning message")
    assert log_file.exists()

    with open(log_file) as f:
        log_contents = f.read()
        assert "Test warning message" in log_contents


def test_configure_logging_handler_cleared():
    configure_logging(level="DEBUG")
    logger = logging.getLogger()
    initial_handlers = len(logger.handlers)

    configure_logging(level="INFO")
    assert (
        len(logger.handlers) == initial_handlers
    )  # Handlers should be cleared and reconfigured

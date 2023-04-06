import logging

from zero_3rdparty.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def test_setup_logging_should_be_idempotent():
    for _ in range(3):
        setup_logging()
    logger.info("msg")
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1

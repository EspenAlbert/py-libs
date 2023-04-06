from __future__ import annotations

import logging
from logging import config

from zero_lib.env_reader import log_format_console, log_max_msg_length
from zero_lib.run_env import running_in_container_environment

logger = logging.getLogger(__name__)


class ReplaceLineBreaks(logging.Filter):
    def filter(self, record):
        if (msg := getattr(record, "msg", None)) and isinstance(msg, str):
            record.msg = record.msg.replace("\n", "\\n\t")
        return super().filter(record)


class LimitMessageLength(logging.Filter):
    def __init__(self, length=1000, name=""):
        super().__init__(name)
        self.length = length

    def filter(self, record: logging.LogRecord) -> int:
        if (
            (msg := getattr(record, "msg", None))
            and isinstance(msg, str)
            and len(msg) > self.length
        ):
            record.msg = record.msg[: self.length]
        return super().filter(record)


def limit_message_length(logger: logging.Logger = None) -> None:
    max_length = log_max_msg_length()
    filter = LimitMessageLength(length=max_length)
    if logger is None:
        logger = logging.getLogger()
        logger.warning(f"adding limit message length={max_length} to handlers!")
        for handler in logger.handlers:
            handler.addFilter(filter)
    else:
        logger.addFilter(filter)


def avoid_linebreaks(logger: logging.Logger = None):
    replace_line_breaks_filter = ReplaceLineBreaks()
    if logger is None:
        logger = logging.getLogger()
        logger.warning("adding replace line breaks to handlers!")
        for handler in logger.handlers:
            handler.addFilter(replace_line_breaks_filter)
    else:
        logger.addFilter(replace_line_breaks_filter)


DATE_FMT_SHORT = "%H:%M:%S"
DATE_FMT_LONG = "%Y-%m-%dT%H:%M:%S"


def default_handler() -> dict:
    return {
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stdout",
        "level": logging.INFO,
    }


def setup_logging(
    handler_dict: dict | None = None, disable_stream_handler: bool = False
):
    handlers = {} if disable_stream_handler else {"stream": default_handler()}
    if handler_dict:
        handlers["default"] = handler_dict
    assert handlers, "no logging handlers are configured!"
    for handler in handlers.values():
        handler["formatter"] = "default"
    config.dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "class": "logging.Formatter",
                    "format": log_format_console(),
                    "datefmt": DATE_FMT_LONG,
                }
            },
            "handlers": handlers,
            "root": {"handlers": list(handlers.keys()), "level": logging.INFO},
            "disable_existing_loggers": False,
        }
    )
    if running_in_container_environment():
        avoid_linebreaks()
        #: dispatcher logging a VectorMap can take up many 1000 symbols.
        limit_message_length()

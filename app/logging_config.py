import logging

import structlog

from app.middleware import request_id_ctx


def _add_request_id(logger, method_name, event_dict):
    event_dict["request_id"] = request_id_ctx.get()
    return event_dict


def configure_logging():
    logging.basicConfig(format="%(message)s", level=logging.INFO)

    structlog.configure(
        processors=[
            _add_request_id,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(**initial_context):
    return structlog.get_logger(**initial_context)
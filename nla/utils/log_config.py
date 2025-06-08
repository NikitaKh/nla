import logging
from pathlib import Path

import structlog


def configure_struct_logger(log_path: Path | None = None):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(
            file=Path(log_path).open("a+t") if log_path else None
        ),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()

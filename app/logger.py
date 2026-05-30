# app/logging.py

import logging
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    """
    把标准 logging 的日志转发到 loguru。

    这样 uvicorn / fastapi / sqlalchemy 这些用 logging 的库，
    也能被 loguru 接管。
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2

        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())


def setup_logging(debug: bool = False) -> None:
    """
    初始化 loguru。
    """

    logger.remove()

    log_level = "DEBUG" if debug else "INFO"

    logger.add(
        sys.stdout,
        level=log_level,
        colorize=True,
        enqueue=True,
        backtrace=debug,
        diagnose=debug,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    # 可选：写入文件
    logger.add(
        "logs/sakura-core.log",
        level=log_level,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        encoding="utf-8",
        backtrace=debug,
        diagnose=debug,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
    )

    # 接管标准 logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 接管常见 logger
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "sqlalchemy",
    ):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False

    logger.info("Logging initialized. level={}", log_level)

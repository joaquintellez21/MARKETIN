"""Logging configuration."""

import logging
import sys
from config import Config


def setup_logger(name: str = "polymarket_bot") -> logging.Logger:
    config = Config()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        console.encoding = "utf-8"
        logger.addHandler(console)

        file_handler = logging.FileHandler("bot.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

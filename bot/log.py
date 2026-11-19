"""
Logging setup: every message goes to the screen (visible in the GitHub
Actions run page) AND to logs/bot.log (committed to the repo so you can read
it on your phone).
"""

import logging
import time

from bot import config


def get_logger(name: str = "bot") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # already set up
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s UTC | %(levelname)s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fmt.converter = time.gmtime  # always log in UTC

    screen = logging.StreamHandler()
    screen.setFormatter(fmt)
    logger.addHandler(screen)

    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger

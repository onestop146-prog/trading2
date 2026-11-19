# Send test log messages to a throwaway file instead of the real logs/bot.log.
# This runs before the tests import the rest of the bot.
import tempfile
from pathlib import Path

from bot import config

config.LOG_FILE = Path(tempfile.mkdtemp()) / "test.log"

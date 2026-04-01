from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("file.log", rotation="10 MB", level="DEBUG")
